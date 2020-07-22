'''
Models for Discriminator Experiment

Peter Wu
peterw1@andrew.cmu.edu
'''

import torch
import torch.nn as nn

from torch.autograd import Variable
from torch.distributions.bernoulli import Bernoulli

class SimpleLSTMDiscriminator(nn.Module):
    def __init__(self, vocab_size, num_layers=2, word_dropout=0.2, emb_dim=300, hidden_dim=650):
        super(SimpleLSTMDiscriminator, self).__init__()
        self.num_layers = num_layers
        self.hidden_dim = hidden_dim
        self.prob_keep = 1-word_dropout
        self.emb_mat = nn.Embedding(vocab_size, emb_dim)
        self.rnn = nn.LSTM(emb_dim, hidden_dim, batch_first=True, num_layers=num_layers, dropout=0.35, bidirectional=True)
        self.fc = nn.Sequential(
            nn.ReLU(),
            nn.Linear(hidden_dim*2, 2)
        )

    def forward(self, x):
        x_emb = self.emb_mat(x) # shape: (batch_size, seq_len, emb_dim)
        if self.training:
            rw = Bernoulli(self.prob_keep).sample((x_emb.shape[1], ))
            x_emb = x_emb[:, rw==1] # (batch_size, new_seq_len, emb_dim)
        _, (h, _) = self.rnn(x_emb)
        h = h.view(self.num_layers, 2, -1, self.hidden_dim) # num_layers, 2, batch_size, hidden_dim)
        h = torch.cat([h[-1][0], h[-1][1]], 1) # (batch_size, 2*hidden_dim)
        out = self.fc(h)
        return out

class LSTMDiscriminator(nn.Module):
    '''
    As described in: https://arxiv.org/abs/1810.11895
    '''
    def __init__(self, vocab_size,  num_layers=1, word_dropout=0.2, emb_dim=300, hidden_dim=650):
        super(LSTMDiscriminator, self).__init__()
        self.num_layers = num_layers
        self.hidden_dim = hidden_dim
        self.prob_keep = 1-word_dropout
        self.emb_mat = nn.Embedding(vocab_size, emb_dim)
        self.rnn = nn.LSTM(emb_dim, hidden_dim, batch_first=True, num_layers=num_layers, dropout=0.35, bidirectional=True)
        self.w = nn.Parameter(torch.randn(2*hidden_dim))

    def forward_repr(self, x):
        '''
        Args:
            x: LongTensor with shape (batch_size, seq_len)
        '''
        x_emb = self.emb_mat(x) # shape: (batch_size, seq_len, emb_dim)
        if self.training:
            rw = Bernoulli(self.prob_keep).sample((x_emb.shape[1], ))
            x_emb = x_emb[:, rw==1] # (batch_size, new_seq_len, emb_dim)
        _, (h, _) = self.rnn(x_emb)
        h = h.view(self.num_layers, 2, -1, self.hidden_dim) # num_layers, 2, batch_size, hidden_dim)
        h = torch.cat([h[-1][0], h[-1][1]], 1) # (batch_size, 2*hidden_dim)
        return h

    def forward_score(self, x):
        '''
        Args:
            x: LongTensor with shape (batch_size, seq_len)
        
        Args:
            score: FloatTensor with shape (batch_size,)
        '''
        h = self.forward_repr(x)
        score = (self.w[None, :]*h).sum(1)
        return score

    def forward(self, x):
        return self.forward_score(x)

class WERDiscriminatorLoss(nn.Module):
    def __init__(self):
        super(WERDiscriminatorLoss, self).__init__()

    def forward(self, true_scores, gens_scores, cers):
        '''
        Args:
            true_scores: shape (batch_size,)
            gens_scores: shape (batch_size,)
            cers:        shape (batch_size,)
        
        Return:
            float tensor
        '''
        loss = torch.clamp(cers/100 - (true_scores-gens_scores), min=0)
        return torch.mean(loss)


class LSTMLM(nn.Module):
    def __init__(self, vocab_size, args):
        super(LSTMLM, self).__init__()
        self.hidden_dim = args.hidden_dim
        self.emb_mat = nn.Embedding(vocab_size, args.emb_dim)
        self.rnn_cell = nn.LSTMCell(args.emb_dim, self.hidden_dim)
        self.char_projection = nn.Sequential(
            nn.Linear(self.hidden_dim, vocab_size)
        )
        self.force_rate = args.teacher_force_rate

    def forward_step(self, prev_char, prev_hidden):
        '''
        Args:
            prev_char: shape (batch_size,)
            prev_hidden: pair of tensors with shape (batch_size, hidden_dim)

        Return:
            logits: tensor with shape (batch_size, vocab_size)
            y_pred: tensor with shape (batch_size,)
            new_hidden: pair of tensors with shape (batch_size, hidden_dim)
        '''
        emb = self.emb_mat(prev_char) # (batch_size, emb_dim)
        h, c = self.rnn_cell(emb, prev_hidden) # h shape: (batch_size, hidden_dim)
        logits = self.char_projection(h)
        y_pred = torch.max(logits, 1)[1]
        return logits, y_pred, (h, c)

    def forward(self, x, lens):
        '''
        Args:
            x: tensor with shape (maxlen, batch_size)
            lens: tensor with shape (batch_size,), comprised of
                length of each input sequence in batch
        '''
        maxlen, batch_size = x.shape

        hidden = (torch.randn(batch_size, self.hidden_dim), torch.randn(batch_size, self.hidden_dim))
        all_logits = []
        y_preds = []
        for i in range(maxlen):
            if len(y_preds) > 0 and self.force_rate < 1 and self.training:
                forced_char = x[i, :] # shape: (batch_size,)
                gen_char = y_preds[-1]
                force_mask = Variable(forced_char.data.new(*forced_char.size()).bernoulli_(self.force_rate))
                char = (force_mask * forced_char) + ((1 - force_mask) * gen_char)
            else:
                char = x[i, :]
            logits, y_pred, hidden = self.forward_step(char, hidden)
            all_logits.append(logits)
            y_preds.append(y_pred)
        all_logits = torch.stack(all_logits, 0) # shape: (maxlen, batch_size, vocab_size)
        y_preds = torch.stack(y_preds, 1) # shape: (batch_size, maxlen)
        return all_logits, y_preds
