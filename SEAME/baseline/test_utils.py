'''
Code to e.g. calculate MER or top-k CER

Peter Wu
peterw1@andrew.cmu.edu
'''

import argparse
import csv
import itertools
import numpy as np
import os
import re
import sys
import time
import torch

from autocorrect import spell
from nltk.metrics import edit_distance
from torch.autograd import Variable
from torch.utils.data import DataLoader, Dataset

from baseline import parse_args, Seq2SeqModel, write_transcripts
from model_utils import *


def is_chinese_char(ch):
    curr_ord = ord(ch)
    if 11904 <= curr_ord and curr_ord <= 12031:
        return True
    elif 12352 <= curr_ord and curr_ord <= 12543:
        return True
    elif 13056 <= curr_ord and curr_ord <= 19903:
        return True
    elif 19968 <= curr_ord and curr_ord <= 40959:
        return True
    elif 63744 <= curr_ord and curr_ord <= 64255:
        return True
    elif 65072 <= curr_ord and curr_ord <= 65103:
        return True
    elif 194560 <= curr_ord and curr_ord <= 195103:
        return True
    else:
        return False


def closest_word(word, vocab, threshold=5, sub_thres=2):
    '''Finds closest word in the vocabulary (w.r.t. edit distance)

    Returns 2 words if no closest word found
    '''
    best_word = word
    best_dist = float("inf")
    prefix_len_best = float("inf")
    for vocab_word in vocab:
        curr_dist = edit_distance(word, vocab_word)
        if curr_dist < best_dist:
            best_dist = curr_dist
            best_word = vocab_word
            prefix_len_best = len(os.path.commonprefix([word, vocab_word]))
        elif curr_dist == best_dist and abs(len(best_word)-len(word)) > abs(len(vocab_word)-len(word)):
            prefix_len_vocab = len(os.path.commonprefix([word, vocab_word]))
            if prefix_len_best < prefix_len_vocab:
                best_word = vocab_word
                prefix_len_best = prefix_len_vocab
    if best_dist > 5: # margin of error is sub_thres for each subword
        for i in range(len(word)-1):
            word1 = word[:i+1]
            word2 = word[i+1:]
            curr_dist = float("inf")
            vocab_word1 = word1
            for vocab_word in vocab:
                if word1 == vocab_word:
                    vocab_word1 = vocab_word
                    curr_dist = 0
                    break
                dist1 = edit_distance(word1, vocab_word)
                if dist1 < curr_dist:
                    vocab_word1 = vocab_word
                    curr_dist = dist1
            vocab_word2 = word2
            if curr_dist <= sub_thres:
                curr_dist2 = float("inf")
                for vocab_word in vocab:
                    if word2 == vocab_word:
                        vocab_word2 = vocab_word
                        curr_dist2 = 0
                        break
                    dist2 = edit_distance(word2, vocab_word)
                    if dist2 < curr_dist2:
                        vocab_word2 = vocab_word
                        curr_dist2 = dist2
                curr_dist += curr_dist2
                if curr_dist < best_dist:
                    best_word = vocab_word1+' '+vocab_word2
                    best_dist = curr_dist
    return best_word


def mk_map(vocab):
    '''
    chinese characters are mapped to themselves and english words are
    mapped to unique unicode characters

    Assumes that vocab is only comprised of single chinese characters and
    english words

    Args:
        vocab: set of strings
    
    Return:
        wmap: dict, i.e. {str: new_str}, where each str is a token
    '''
    curr_unicode_num = 0
    wmap = {}
    for w in vocab:
        if is_chinese_char(w[0]):
            wmap[w] = w
        else:
            curr_unicode_ch = chr(curr_unicode_num)
            while curr_unicode_ch in vocab:
                curr_unicode_num += 1
                curr_unicode_ch = chr(curr_unicode_num)
            wmap[w] = curr_unicode_ch
            curr_unicode_num += 1
    return wmap

def map_lines(lines, wmap):
    '''
    Assumes that all words are either only composed of chinese characters or
    only composed of english letters
    '''
    new_lines = []
    for l in lines:
        l_list = l.split()
        new_l_list = []
        for w in l_list:
            if is_chinese_char(w[0]):
                new_l_list.append(w)
            else:
                new_l_list.append(wmap[w])
        new_l = ' '.join(new_l_list)
        new_lines.append(new_l)
    return new_lines

def get_mer(save_dir='output/baseline/v1'):
    t0 = time.time()
    test_ys = load_y_data('test') # 1-dim np array of strings
    CSV_PATH = os.path.join(save_dir, 'submission.csv')
    transcripts = []
    with open(CSV_PATH, 'r') as csvfile:
        raw_csv = csv.reader(csvfile)
        for row in raw_csv:
            transcripts.append(row[1])
    t1 = time.time()
    print('loaded data (%.2f seconds)' % (t1-t0))

    test_ys_spaced = []
    for test_y in test_ys:
        curr_s = ''
        next_ch = test_y[0] # for scope
        for s_i, ch in enumerate(test_y[:-1]):
            next_ch = test_y[s_i+1]
            curr_s += ch
            ch_is_chinese = is_chinese_char(ch)
            next_ch_is_chinese = is_chinese_char(next_ch)
            if (ch_is_chinese and not next_ch_is_chinese) or (next_ch_is_chinese and not ch_is_chinese):
                curr_s += ' '
        curr_s += next_ch
        test_ys_spaced.append(curr_s)
    YS_SPACED_PATH = os.path.join(save_dir, 'ys_spaced.txt')
    with open(YS_SPACED_PATH, 'w+') as ouf:
        for l in test_ys_spaced:
            ouf.write('%s\n' % l)

    test_ys_eng = []
    for test_y in test_ys:
        curr_s = ''
        for ch in test_y:
            if not is_chinese_char(ch):
                curr_s += ch
        test_ys_eng.append(curr_s)
    test_ys_eng = [l.strip() for l in test_ys_eng]

    transcripts_spaced = []
    for transcript in transcripts:
        curr_s = ''
        next_ch = test_y[0] # for scope
        for s_i, ch in enumerate(transcript[:-1]):
            next_ch = transcript[s_i+1]
            curr_s += ch
            ch_is_chinese = is_chinese_char(ch)
            next_ch_is_chinese = is_chinese_char(next_ch)
            if (ch_is_chinese and not next_ch_is_chinese) or (next_ch_is_chinese and not ch_is_chinese):
                curr_s += ' '
        curr_s += next_ch
        transcripts_spaced.append(curr_s)
    TRANSCRIPTS_SPACED_PATH = os.path.join(save_dir, 'transcripts_spaced.txt')
    with open(TRANSCRIPTS_SPACED_PATH, 'w+') as ouf:
        for l in transcripts_spaced:
            ouf.write('%s\n' % l)

    AUTOCORRECT_PATH = os.path.join(save_dir, 'transcript_autoc.txt')
    PROX_PATH = os.path.join(save_dir, 'transcript_prox.txt')
    AUTOC_PROX_PATH = os.path.join(save_dir, 'transcript_autoc_prox.txt')

    if not os.path.exists(AUTOCORRECT_PATH) or not os.path.exists(PROX_PATH) or not os.path.exists(AUTOC_PROX_PATH):
        t1 = time.time()
        print('generating transcripts (at %.2f seconds)' % (t1-t0))
        test_eng_vocab = set()
        for test_y in test_ys_eng:
            test_y_list = test_y.split()
            for word in test_y_list:
                test_eng_vocab.add(word)

        transcripts_spaced_lists = [l.split() for l in transcripts_spaced]

        new_transcripts_autoc = []
        new_transcripts_prox = []
        new_transcripts_autoc_prox = []
        for i, l_list in enumerate(transcripts_spaced_lists):
            l_list_a = l_list.copy()
            l_list_p = l_list.copy()
            l_list_ap = l_list.copy()
            for word_i, w in enumerate(l_list): # assumes that all words in the list are monolingual
                if not is_chinese_char(w[0]):
                    new_a_word = w
                    new_p_word = w
                    new_ap_word = w
                    if w not in test_eng_vocab:
                        new_a_word = spell(w)
                        new_p_word = closest_word(w, test_eng_vocab)
                    if new_a_word in test_eng_vocab:
                        new_ap_word = new_a_word
                    else:
                        new_ap_word = new_p_word
                    l_list_a[word_i] = new_a_word
                    l_list_p[word_i] = new_p_word
                    l_list_ap[word_i] = new_ap_word
            new_l_a = ' '.join(l_list_a)
            new_l_p = ' '.join(l_list_p)
            new_l_ap = ' '.join(l_list_ap)
            new_transcripts_autoc.append(new_l_a)
            new_transcripts_prox.append(new_l_p)
            new_transcripts_autoc_prox.append(new_l_ap)
            if (i+1) % 500 == 0:
                t1 = time.time()
                print('Processed %d Lines (at %.2f seconds)' % (i+1, t1-t0))

        with open(AUTOCORRECT_PATH, 'w+') as ouf:
            for curr_s in new_transcripts_autoc:
                ouf.write('%s\n' % curr_s)

        with open(PROX_PATH, 'w+') as ouf:
            for curr_s in new_transcripts_prox:
                ouf.write('%s\n' % curr_s)

        with open(AUTOC_PROX_PATH, 'w+') as ouf:
            for curr_s in new_transcripts_autoc_prox:
                ouf.write('%s\n' % curr_s)
    else:
        with open(AUTOCORRECT_PATH, 'r') as inf:
            new_transcripts_autoc = inf.readlines()
        new_transcripts_autoc = [l.strip() for l in new_transcripts_autoc]
        with open(PROX_PATH, 'r') as inf:
            new_transcripts_prox = inf.readlines()
        new_transcripts_prox = [l.strip() for l in new_transcripts_prox]
        with open(AUTOC_PROX_PATH, 'r') as inf:
            new_transcripts_autoc_prox = inf.readlines()
        new_transcripts_autoc_prox = [l.strip() for l in new_transcripts_autoc_prox]


    # ------------------------------------------
    # mer when vocab is test vocab
    # i.e. for new_transcripts_prox and new_transcripts_autoc_prox
    t1 = time.time()
    print('calculating mer values (at %.2f seconds)' % (t1-t0))
    test_vocab = set() # composed of single chinese characters and english words
    for test_y in test_ys_spaced:
        test_y_list = test_y.split()
        for word in test_y_list:
            if is_chinese_char(word[0]):
                for ch in word:
                    test_vocab.add(ch)
            else:
                test_vocab.add(word)
    test_vocab.add(' ')
    test_map = mk_map(test_vocab)

    prox_vocab = test_vocab.copy()
    for l in new_transcripts_prox:
        l_list = l.split()
        for word in l_list:
            if is_chinese_char(word[0]):
                for ch in word:
                    prox_vocab.add(ch)
            else:
                prox_vocab.add(word)
    prox_map = mk_map(prox_vocab)

    autoc_prox_vocab = test_vocab.copy()
    for l in new_transcripts_autoc_prox:
        l_list = l.split()
        for word in l_list:
            if is_chinese_char(word[0]):
                for ch in word:
                    autoc_prox_vocab.add(ch)
            else:
                autoc_prox_vocab.add(word)
    autoc_prox_map = mk_map(autoc_prox_vocab)

    transcripts_prox_uni = map_lines(new_transcripts_prox, prox_map)
    test_ys_spaced_uni = map_lines(test_ys_spaced, prox_map)
    PROX_MER_LOG_PATH = os.path.join(save_dir, 'prox_mer_log.txt')
    PROX_MER_PATH = os.path.join(save_dir, 'prox_mer.npy')
    PROX_DIST_PATH = os.path.join(save_dir, 'prox_dist.npy')
    prox_norm_dists, prox_dists = cer_from_transcripts(transcripts_prox_uni, test_ys_spaced_uni, PROX_MER_LOG_PATH)
    np.save(PROX_MER_PATH, prox_norm_dists)
    np.save(PROX_DIST_PATH, prox_dists)
    print('prox avg mer:', np.mean(prox_norm_dists))
    t1 = time.time()
    print('At %.2f seconds' % (t1-t0))

    transcripts_autoc_prox_uni = map_lines(new_transcripts_autoc_prox, autoc_prox_map)
    test_ys_spaced_autoc_prox_uni = map_lines(test_ys_spaced, autoc_prox_map)
    AUTOC_PROX_MER_LOG_PATH = os.path.join(save_dir, 'autoc_prox_mer_log.txt')
    AUTOC_PROX_MER_PATH = os.path.join(save_dir, 'autoc_prox_mer.npy')
    AUTOC_PROX_DIST_PATH = os.path.join(save_dir, 'autoc_prox_dist.npy')
    autoc_prox_norm_dists, autoc_prox_dists = cer_from_transcripts(transcripts_autoc_prox_uni, test_ys_spaced_autoc_prox_uni, AUTOC_PROX_MER_LOG_PATH)
    np.save(AUTOC_PROX_MER_PATH, autoc_prox_norm_dists)
    np.save(AUTOC_PROX_DIST_PATH, autoc_prox_dists)
    print('autoc prox avg mer:', np.mean(autoc_prox_norm_dists))
    t1 = time.time()
    print('At %.2f seconds' % (t1-t0))

    # ------------------------------------------
    # mer when vocab includes autoc
    # i.e. for new_transcripts_autoc
    autoc_vocab = test_vocab.copy()
    for l in new_transcripts_autoc:
        l_list = l.split()
        for word in l_list:
            if is_chinese_char(word[0]):
                for ch in word:
                    autoc_vocab.add(ch)
            else:
                autoc_vocab.add(word)
    autoc_map = mk_map(autoc_vocab)

    transcripts_autoc_uni = map_lines(new_transcripts_autoc, autoc_map)
    test_ys_spaced_autoc_uni = map_lines(test_ys_spaced, autoc_map)
    AUTOC_MER_LOG_PATH = os.path.join(save_dir, 'autoc_mer_log.txt')
    AUTOC_MER_PATH = os.path.join(save_dir, 'autoc_mer.npy')
    AUTOC_DIST_PATH = os.path.join(save_dir, 'autoc_dist.npy')
    autoc_norm_dists, autoc_dists = cer_from_transcripts(transcripts_autoc_uni, test_ys_spaced_autoc_uni, AUTOC_MER_LOG_PATH)
    np.save(AUTOC_MER_PATH, autoc_norm_dists)
    np.save(AUTOC_DIST_PATH, autoc_dists)
    print('autoc avg mer:', np.mean(autoc_prox_norm_dists))
    t1 = time.time()
    print('At %.2f seconds' % (t1-t0))

def get_topk_cer(save_dir='output/baseline/beam'):
    t0 = time.time()
    test_ys = load_y_data('test') # 1-dim np array of strings
    CSV_PATH = os.path.join(save_dir, 'submission_beam_5_all.csv')
    
    raw_ids = []
    raw_beams = [] # list of list of strings
    
    with open(CSV_PATH, 'r') as csvfile:
        raw_csv = csv.reader(csvfile)
        for row in raw_csv:
            raw_ids.append(row[0])
            raw_beams.append(row[1])
    t1 = time.time()
    print('loaded data (%.2f seconds)' % (t1-t0))

    num_beams = 0
    for curr_id in raw_ids:
        if curr_id == raw_ids[0]:
            num_beams += 1
        else:
            break

    test_ys_rep = []
    for y in test_ys:
        test_ys_rep += [y]*num_beams

    print('computing CER for all test samples (at %.2f seconds)' % (t1-t0))

    CER_LOG_PATH = os.path.join(save_dir, 'cer_log.txt')
    raw_norm_dists, raw_dists = cer_from_transcripts(raw_beams, test_ys_rep, CER_LOG_PATH)
    CER_PATH = os.path.join(save_dir, 'test_cer.npy')
    DIST_PATH = os.path.join(save_dir, 'test_dist.npy')
    raw_norm_dists = np.array(raw_norm_dists)
    raw_dists = np.array(raw_dists)
    norm_dists = raw_norm_dists.reshape((len(test_ys), num_beams))
    dists = raw_dists.reshape((len(test_ys), num_beams))
    np.save(CER_PATH, norm_dists)
    np.save(DIST_PATH, dists)
    
    min_cers = np.min(norm_dists, 1) # shape: (num_ys,)
    min_idxs = np.argmin(norm_dists, 1) # shape: (num_ys,)
    MIN_CERS_PATH = os.path.join(save_dir, 'min_cers.npy')
    MIN_IDXS_PATH = os.path.join(save_dir, 'min_idxs.npy')
    np.save(MIN_CERS_PATH, min_cers)
    np.save(MIN_IDXS_PATH, min_idxs)
    
    print('avg top-k CER:', np.mean(min_cers))

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--save-directory', type=str, default='output/baseline/v1', help='output directory')
    parser.add_argument('--mode', type=str, default='mer', help='mer or topk')
    return parser.parse_args()

def main():
    args = parse_args()
    if args.mode == 'mer':
        get_mer(save_dir=args.save_directory)
    else:
        get_topk_cer()

if __name__ == '__main__':
    main()