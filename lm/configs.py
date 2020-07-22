import argparse
import torch
from datetime import datetime


def str2bool(value):
    return value.lower() == 'true'

# training script parser
parser = argparse.ArgumentParser(description='Language model parameters.')
parser.add_argument('--epoch', help='maximum training epochs', type=int, default=20)
parser.add_argument('--model', help='choose language model', default='lstm')
parser.add_argument('--batch', help='batch size', type=int, default=64)
parser.add_argument('--embed_en', help='pre-trained word embedding for English')
parser.add_argument('--embed_cn', help='pre-trained word embedding for Chinese')
parser.add_argument('--hidden', help='LSTM hidden unit size', type=int, default=512)
parser.add_argument('--embed', help='word embedding vector size', type=int, default=300)
parser.add_argument('--ngram', help='ngram language model', type=int, default=1)
parser.add_argument('--maxlen', help='maximum length of sentence', type=int, default=30)
parser.add_argument('--optim', help='optimizer: adadelta, adam or sgd', default='adam')
parser.add_argument('--dp', help='dropout rate, float number from 0 to 1.', default=0.5, type=float)
parser.add_argument('--mode', help='train/test', default='train')
parser.add_argument('--nworkers', help='number of workers for loading dataset', default=12)
parser.add_argument('--lr', help='initial learning rate', type=float, default=1e-4)
parser.add_argument('--mm', help='momentum', type=float, default=0.9)
parser.add_argument('--clip', help='gradient clipping', type=float, default=0.25)
parser.add_argument('--data', help='dataset path', type=str, default='../SEAME/data')
parser.add_argument('--subset', help='subset size', type=float, default=1.0)
parser.add_argument('--models_dir', help='save model dir', type=str, default='models')
parser.add_argument('--log_dir', help='logging dir', type=str, default='log')
parser.add_argument('--gpu_id', help='GPU to be used if any', type=int, default=0)
parser.add_argument('--qg', help='use QG dataset for data augumentation', type=bool, default=False)
parser.add_argument('--dataset', help='dataset to train LM', type=str, default='seame')
parser.add_argument('--finetune', help='fine tune on pre-trained model', type=str2bool, default=False)
parser.add_argument('--model_path', help='pre-trained model path', type=str, default='models/best.pt')
parser.add_argument('--lm-path', type=str, default='models/best_hd_1024_full.pt', help='Path to language model used for reranking')
parser.add_argument('--submission-csv', type=str, default=' data/submission.csv', help='Model output csv file')
args = parser.parse_args()

# running configurations
log_dir = args.log_dir
timestamp = datetime.now().strftime('%m%d-%H%M%S')
names = ('train', 'dev') if args.mode == 'train' else ('test',)

USE_CUDA = torch.cuda.is_available()
DEVICE = torch.device('cuda:{}'.format(args.gpu_id) if torch.cuda.is_available() else 'cpu')


