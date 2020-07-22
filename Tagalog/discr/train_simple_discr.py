'''
Discriminator Training Script

Peter Wu
peterw1@andrew.cmu.edu
'''

import argparse
import csv
import itertools
import numpy as np
import os
import sys
import time
import torch

from torch import nn
from torch.autograd import Variable
from torch.nn.utils.rnn import PackedSequence
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

from discr_utils import *
from model import *


def parse_args():
    parser = argparse.ArgumentParser()
    
    parser.add_argument('--batch-size', type=int, default=64, metavar='N', help='batch size')
    parser.add_argument('--save-directory', type=str, default='output/v1', help='output directory')
    parser.add_argument('--epochs', type=int, default=50, metavar='N', help='number of epochs')
    parser.add_argument('--patience', type=int, default=10, help='patience for early stopping')
    parser.add_argument('--num-workers', type=int, default=2, metavar='N', help='number of workers')
    parser.add_argument('--cuda', type=int, default=0, help='CUDA device')

    parser.add_argument('--lr', type=float, default=1e-3, metavar='N', help='learning rate')
    parser.add_argument('--weight-decay', type=float, default=1e-5, metavar='N', help='weight decay')
    parser.add_argument('--teacher-force-rate', type=float, default=0.9, metavar='N', help='teacher forcing rate')

    parser.add_argument('--word-dropout', type=float, default=0.1, metavar='N', help='word dropout')
    
    parser.add_argument('--num-layers', type=int, default=2, metavar='N', help='number of LSTM layers')
    parser.add_argument('--emb-dim', type=int, default=300, metavar='N', help='hidden dimension')
    parser.add_argument('--hidden-dim', type=int, default=650, metavar='N', help='hidden dimension')

    parser.add_argument('--beam-file', type=str, default='preds.csv', help='beam outputs file')

    return parser.parse_args()


def main():
    args = parse_args()

    t0 = time.time()

    if not os.path.exists(args.save_directory):
        os.makedirs(args.save_directory)
    log_path = os.path.join(args.save_directory, 'log')
    with open(log_path, 'w+') as ouf:
        pass
    
    print("Loading File IDs and Y Data")
    train_fids, train_orig = load_fid_and_y_data('train')
    train_fid_to_orig = mk_fid_to_orig(train_fids, train_orig)
    dev_fids, dev_orig = load_fid_and_y_data('dev')
    dev_fid_to_orig = mk_fid_to_orig(dev_fids, dev_orig)
    fid_to_gens = load_gens()
    fid_to_gens = simplify_gens(fid_to_gens, train_fid_to_orig)
    fid_to_gens = simplify_gens(fid_to_gens, dev_fid_to_orig)
    num_train, num_train_orig, num_train_gen = count_data(fid_to_gens, train_fid_to_orig)
    num_dev, num_dev_orig, num_dev_gen = count_data(fid_to_gens, dev_fid_to_orig)
    print('train: real - %d,\tfake - %d' % (num_train_orig, num_train_gen))
    print('dev:   real - %d,\tfake - %d' % (num_dev_orig, num_dev_gen))
    t1 = time.time()
    print_log('%.2f Seconds' % (t1-t0), log_path)

    print("Building Charset")
    charset = build_charset(np.concatenate((train_orig, dev_orig), axis=0))
    charmap = make_charmap(charset) # {string: int}
    charcount = len(charset)
    t1 = time.time()
    print_log('%.2f Seconds' % (t1-t0), log_path)

    print("Mapping Characters")
    train_fid_to_orig = map_characters_orig(train_fid_to_orig, charmap)
    dev_fid_to_orig = map_characters_orig(dev_fid_to_orig, charmap)
    fid_to_gens = map_characters_gens(fid_to_gens, charmap)
    t1 = time.time()
    print_log('%.2f Seconds' % (t1-t0), log_path)

    print("Building Loader")
    train_loader = make_simple_loader(train_fid_to_orig, fid_to_gens, args, shuffle=True, batch_size=args.batch_size)
    dev_loader = make_simple_loader(dev_fid_to_orig, fid_to_gens, args, shuffle=False, batch_size=args.batch_size)
    t1 = time.time()
    print_log('%.2f Seconds' % (t1-t0), log_path)

    print("Building Model")
    model = SimpleLSTMDiscriminator(charcount, num_layers=args.num_layers, word_dropout=args.word_dropout, emb_dim=args.emb_dim, hidden_dim=args.hidden_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    criterion = nn.CrossEntropyLoss()
    t1 = time.time()
    print_log(model, log_path)
    print_log('%.2f Seconds' % (t1-t0), log_path)
    
    print("Running")
    ckpt_path = os.path.join(args.save_directory, 'discr.ckpt')
    if os.path.exists(ckpt_path):
        model.load_state_dict(torch.load(ckpt_path))
    if torch.cuda.is_available():
        model = model.cuda(args.cuda)

    best_val_loss = sys.maxsize
    prev_best_epoch = 0
    for e in range(args.epochs):
        t1 = time.time()
        print_log('Starting Epoch %d (%.2f Seconds)' % (e+1, t1-t0), log_path)

        # train
        model.train()
        optimizer.zero_grad()
        l = 0
        for i, (xs, ys) in enumerate(train_loader):
            xs, ys = Variable(xs), Variable(ys)
            if torch.cuda.is_available():
                xs, ys = xs.cuda(args.cuda), ys.cuda(args.cuda)
            logits = model(xs)
            loss = criterion(logits, ys)
            l += loss.item()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 0.25)
            optimizer.step()
            if (i+1) % 100 == 0:
                t1 = time.time()
                print('Processed %d Batches (%.2f Seconds)' % (i+1, t1-t0))
        print_log('Train Loss: %f' % (l/num_train), log_path)
        
        # val
        model.eval()
        with torch.no_grad():
            l = 0
            num_correct = 0.0
            for i, (xs, ys) in enumerate(dev_loader):
                xs, ys = Variable(xs), Variable(ys)
                if torch.cuda.is_available():
                    xs, ys = xs.cuda(args.cuda), ys.cuda(args.cuda)
                logits = model(xs)
                loss = criterion(logits, ys)
                _, y_pred = torch.max(logits, 1)
                l += loss.item()
                num_correct = num_correct + (ys == y_pred).sum()
            val_loss = l/num_dev
            val_acc = (num_correct.float()/num_dev).cpu().item()
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                prev_best_epoch = e
                torch.save(model.state_dict(), ckpt_path)
            elif e - prev_best_epoch > args.patience:
                break
            print_log('Val Loss: %f' % val_loss, log_path)
            print_log('Val Acc: %f' % val_acc, log_path)

if __name__ == "__main__":
    main()