__author__ = 'ando'

import numpy as np
from time import time
import logging
import random

import networkx as nx
from itertools import zip_longest

from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from os import path
from collections import Counter
import os.path

logger = logging.getLogger("deepwalk")


def get_adj_matrix(G):
    '''
    :param G:networkx Graph structure
    :return: Return adjacency matrix of G
    '''
    return nx.adjacency_matrix(G, nodelist=sorted(G.nodes()))

def avg_degree(G):
    '''
    Compute the average degree connectivity of graph.
    :param G: a networkx graph
    :return: avg degree
    '''
    return nx.average_degree_connectivity(G)

def get_connected_components(G):
    '''
    Generate connected components as subgraphs.
    :param G:
    :return: a generator of graph formed by the connected components
    '''
    return nx.connected_component_subgraphs(G)
def is_connected(G):
    '''
    Check if the graph is connected
    :param G: networkx Graph structure
    :return: number of connected components
    '''
    connected = nx.is_connected(G)
    if connected:
        return 1
    else:
        return nx.number_connected_components(G)

def __random_walk__(G, path_length, alpha=0, rand=random.Random(), start=None):
    '''
    Returns a truncated random walk.
    :param G: networkx graph
    :param path_length: Length of the random walk.
    :param alpha: probability of restarts.
    :param rand: random number generator
    :param start: the start node of the random walk.
    :return:
    '''

    if start:
        path = [start]
    else:
        # Sampling is uniform w.r.t V, and not w.r.t E
        path = [rand.choice(G.nodes)]

    while len(path) < path_length:
        cur = path[-1]
        if len(G.neighbors(cur)) > 0:
            if rand.random() >= alpha:
                path.append(rand.choice(G.neighbors(cur)))
            else:
                path.append(path[0])
        else:
            break
    return path


def __parse_adjacencylist_unchecked__(f):
    '''
    read the adjacency matrix
    :param f: line stream of the file opened
    :return: the adjacency matrix
    '''
    adjlist = []
    for l in f:
        if l and l[0] != "#":
            adjlist.extend([[int(x) for x in l.strip().split()]])
    return adjlist


def __from_adjlist_unchecked__(adjlist):
    '''
    create graph form the an adjacency list
    :param adjlist: the adjacency matrix
    :return: networkx graph
    '''
    G = nx.Graph()
    G.add_edges_from(adjlist)

    # for edge in adjlist:
    #     '''
    #     node = row[0]
    #     neighbors = row[1:]
    #     edges = list(zip([node] * len(neighbors), neighbors))
    #     '''
    #     edges = [edge[0], edge[1]]
    #     G.add_edges_from(edge)
    return G

def load_adjacencylist(file_, undirected=False, chunksize=10000):
    '''
    multi-threaded function to read the adjacency matrix and build the graph
    :param file_: graph file
    :param undirected: is the graph undirected
    :param chunksize: how many edges for thread
    :return:
    '''

    parse_func = __parse_adjacencylist_unchecked__
    convert_func = __from_adjlist_unchecked__


    adjlist = []

    #read the matrix file
    t0 = time()
    with open(file_) as f:
        with ProcessPoolExecutor(max_workers=cpu_count()) as executor:
            total = 0
            for idx, adj_chunk in enumerate(executor.map(parse_func, grouper(int(chunksize), f))): #execute pare_function on the adiacent list of the file in multipe process
                adjlist.extend(adj_chunk) #merge the results of different process
                total += len(adj_chunk)
    t1 = time()
    adjlist = np.asarray(adjlist)

    logger.info('Parsed {} edges with {} chunks in {}s'.format(total, idx, t1-t0))

    t0 = time()
    G = convert_func(adjlist)
    t1 = time()

    logger.info('Converted edges to graph in {}s'.format(t1-t0))

    if undirected:
        G = G.to_undirected()

    return G


def _write_walks_to_disk(args):
    """
    deprecated function, used to save only the walks and not each example
    :param args:
    :return:
    """
    num_paths, path_length, alpha, rand, f = args
    G = __current_graph
    t_0 = time()
    with open(f, 'w') as fout:
        for walk in build_deepwalk_corpus_iter(G=G, num_paths=num_paths, path_length=path_length, alpha=alpha, rand=rand):
            fout.write(u"{}\n".format(u" ".join(__vertex2str[v] for v in walk)))
    logger.debug("Generated new file {}, it took {} seconds".format(f, time() - t_0))
    return f

def _write_examples_to_disk(args):
    """
    Generate the example to train second order proximity

    :param args: list of arguments
    :return:
    """
    num_paths, path_length, alpha, rand, f, windows_size = args
    G = __current_graph
    t_0 = time()

    def generate_labels(walk):
        """
        helper function used to sample the example form the walks
        :param walk:
        :return:
        """
        for pos, node in enumerate(walk):  # node = input vertex of the sistem
            start = max(0, pos - windows_size)
            # now go over all nodes from the (reduced) window, predicting each one in turn
            for pos2, node2 in enumerate(walk[start: pos + windows_size + 1], start):  # node 2 are the output nodes predicted form node
                start_w = max(0, pos2 - windows_size)
                end_w = min(path_length - 1, pos2 + windows_size)
                windows = walk[start_w: end_w + 1]
                windows.remove(node2)
                # make the windows all the same size
                while len(windows) < 2 * windows_size:
                    windows.append(np.random.choice(windows, replace=False))
                yield (node2, windows)



    with open(f, 'w') as fout:
        for walk in build_deepwalk_corpus_iter(G=G, num_paths=num_paths, path_length=path_length, alpha=alpha, rand=rand):
            for in_label, out_label in generate_labels(walk):
                fout.write("{}\t{}\n".format(in_label, " ".join(__vertex2str[v] for v in out_label)))
    logger.debug("Generated new file {}, it took {} seconds".format(f, time() - t_0))
    return f

# def write_walks_to_disk(G, filebase, num_paths, path_length, alpha=0, rand=random.Random(0), num_workers=cpu_count(), always_rebuild=True):
#     global __current_graph
#     global __vertex2str
#     __current_graph = G
#     __vertex2str = {v:str(v) for v in sorted(G.nodes())}
#     files_list = ["{}.{}".format(filebase, str(x)) for x in range(num_paths)]
#     expected_size = len(G)
#     args_list = []
#     files = []
#
#     if num_paths <= num_workers:
#         paths_per_worker = [1 for x in range(num_paths)]
#     else:
#         paths_per_worker = [len(list(filter(lambda z: z!= None, [y for y in x]))) for x in grouper(int(num_paths / num_workers)+1, range(1, num_paths+1))]
#
#     with ProcessPoolExecutor(max_workers=num_workers) as executor:
#         for size, file_, ppw in zip(executor.map(count_lines, files_list), files_list, paths_per_worker):
#             if always_rebuild or size != (ppw*expected_size):
#                 args_list.append((ppw, path_length, alpha, random.Random(rand.randint(0, 2**31)), file_))
#             else:
#                 files.append(file_)
#
#     with ProcessPoolExecutor(max_workers=num_workers) as executor:
#         for file_ in executor.map(_write_walks_to_disk, args_list):
#             files.append(file_)
#
#     return files
#
def write_walks_to_disk(G, filebase, num_paths, path_length, windows_size, alpha=0, rand=random.Random(0), num_workers=cpu_count(), always_rebuild=True):
    """
    Function used to sample the random walk and generate the example for the second order proximity
    :param filebase: list of file to write
    :param windows_size: windows size for each path
    :param num_workers: num of worker on which split the task
    :param always_rebuild:
    :return:
    """
    global __current_graph
    global __vertex2str
    __current_graph = G
    __vertex2str = {v:str(v) for v in sorted(G.nodes())}
    files_list = ["{}.{}".format(filebase, str(x)) for x in range(num_paths)]
    expected_size = len(G)
    args_list = []
    files = []

    if num_paths <= num_workers:
        paths_per_worker = [1 for x in range(num_paths)]
    else:
        paths_per_worker = [len(list(filter(lambda z: z!= None, [y for y in x]))) for x in grouper(int(num_paths / num_workers)+1, range(1, num_paths+1))]

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        for size, file_, ppw in zip(executor.map(count_lines, files_list), files_list, paths_per_worker):
            if always_rebuild or size != (ppw*expected_size):
                args_list.append((ppw, path_length, alpha, random.Random(rand.randint(0, 2**31)), file_, windows_size))
            else:
                files.append(file_)

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        for file_ in executor.map(_write_examples_to_disk, args_list):
            files.append(file_)

    return files

def combine_example_files_iter(file_list):
    """
    Function used to iterate over all the example generated
    :param file_list: list of files containing the examples
    :return:
    """
    for file in file_list:
        if os.path.isfile(file):
            with open(file, 'r') as f:
                for line in f:
                    tokens = line.strip().split("\t")
                    yield int(tokens[0]), [int(node) for node in tokens[1].split()]


def combine_files_iter(file_list):
    """
    DEPRECATED used to iterate only on the walks
    :param file_list:
    :return:
    """
    for file in file_list:
        if os.path.isfile(file):
            with open(file, 'r') as f:
                for line in f:
                    yield np.array([int(node) for node in line.split()])

def count_lines(f):
    if path.isfile(f):
        num_lines = sum(1 for line in open(f))
        return num_lines
    else:
        return 0

def build_deepwalk_corpus(G, num_paths, path_length, alpha=0, rand=random.Random(0)):
    '''
    extract the walks form the graph used for context embeddings
    :param G: graph
    :param num_paths: how many random walks to form a sentence
    :param path_length: how long each path -> length of the sentence
    :param alpha: restart probability
    :param rand: random function
    :return:
    '''
    walks = []
    nodes = list(G.nodes())
    for cnt in range(num_paths):
        rand.shuffle(nodes)
        for node in nodes:
            walks.append(__random_walk__(G, path_length, rand=rand, alpha=alpha, start=node))
    return np.array(walks)


def build_deepwalk_corpus_iter(G, num_paths, path_length, alpha=0, rand=random.Random(0)):
    """
    Generate the random walks
    :param G: Graph on which walk
    :param num_paths: number of walks to generate for each node
    :param path_length: lengtht of each path
    :param alpha:
    :param rand:
    :return:
    """
    walks = []
    nodes = list(G.nodes())
    for cnt in range(num_paths):
        rand.shuffle(nodes)
        for node in nodes:
            yield __random_walk__(G,path_length, rand=rand, alpha=alpha, start=node)


def count_textfiles(files, workers=1):
    c = Counter()
    with ProcessPoolExecutor(max_workers=workers) as executor:
        for c_ in executor.map(count_words, files):
            c.update(c_)
    return c

def count_words(file):
    """ Counts the word frequences in a list of sentences.

    Note:
      This is a helper function for parallel execution of `Vocabulary.from_text`
      method.
    """
    c = Counter()
    with open(file, 'r') as f:
        for l in f:
            words = [int(word) for word in l.strip().split()]
            c.update(words)
    return c


def grouper(n, iterable, padvalue=None):
    "grouper(3, 'abcdefg', 'x') --> ('a','b','c'), ('d','e','f'), ('g','x','x')"
    return zip_longest(*[iter(iterable)]*n, fillvalue=padvalue)

