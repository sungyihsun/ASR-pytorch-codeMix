import csv
import argparse
import torch
import torch.nn.functional as F

from collections import defaultdict
from utils.data import las_to_lm, is_chinese_word
from configs import *


def rerank(model_path, csv_path):
    if DEVICE == torch.device('cpu'):
        lm = torch.load(model_path, map_location='cpu')
    else:
        lm = torch.load(model_path, map_location='cuda:0')
    lm.to(DEVICE)
    lm.eval()
    transcripts = defaultdict(list)
    with open(csv_path, 'r') as csv_file:
        raw_csv = csv.reader(csv_file)
        for row in raw_csv:
            transcripts[int(row[0])].append(row[1])
    for id, sents in sorted(transcripts.items(), key=lambda x: x[0]):
        res = []
        if any(len(sent) == 0 for sent in sents):
            print("{},{}".format(id, sents[0]))
            continue
        for sent in sents:
            if args.dataset == 'seame' or args.dataset == 'qg':
                _sent = las_to_lm(sent.split())
            else:
                _sent = ['<s>'] + sent.split() + ['<s>']
            targets = torch.LongTensor([lm.vocab[tok] for tok in _sent[1:]]).to(DEVICE)
            logits = lm(_sent)[0]
            loss = F.cross_entropy(logits, targets).item()
            res.append((loss, sent))
        res.sort(key=lambda x: x[0])
        transcripts[id] = [_[1] for _ in res]
        print("{},{}".format(id, transcripts[id][0]))
        #---- Eason
        fp = open('/'.join(csv_path.split('/')[:-1]) + "/result.txt", "a")
        fp.write(transcripts[id][0] + '\n')
        fp.close()
        #2020 07 22
        lm.detach()
    return transcripts


def count_word_num(model_path):
    if DEVICE == torch.device('cpu'):
        lm = torch.load(model_path, map_location='cpu')
    else:
        lm = torch.load(model_path, map_location='cuda:0')
    lm.to(DEVICE)
    print("Total vocab length: ", len(lm.vocab))
    chn_word_num, eng_word_num = 0, 0
    for word in lm.vocab.itos:
        if not is_chinese_word(word):
            eng_word_num += 1
        else:
            chn_word_num += 1
    return chn_word_num, eng_word_num


if __name__ == '__main__':
    # chn, eng = count_word_num(args.lm_path)
    # print("Chinese word amount: {}".format(chn))
    # print("English word amount: {}".format(eng))
    reranked = rerank(args.lm_path, args.submission_csv)
