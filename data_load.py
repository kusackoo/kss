#-*- coding: utf-8 -*-
#/usr/bin/python2
'''
By kyubyong park. kbpark.linguist@gmail.com. 
https://www.github.com/kyubyong/kss
'''

from __future__ import print_function

from hyperparams import Hyperparams as hp
import numpy as np
import tensorflow as tf
from utils import *
import codecs
import re
import os
import unicodedata
from itertools import chain


def load_vocab():
    char2idx = {char: idx for idx, char in enumerate(hp.vocab)}
    idx2char = {idx: char for idx, char in enumerate(hp.vocab)}
    return char2idx, idx2char

def load_data(mode="train"):
    '''Loads data
      Args:
          mode: "train" or "synthesize".
    '''
    # Load vocabulary
    char2idx, idx2char = load_vocab()

    # load conversion dictionaries
    j2hcj, j2sj, j2shcj = load_j2hcj(), load_j2sj(), load_j2shcj()

    if mode=="train":
        # Parse
        fpaths, text_lengths, texts = [], [], []
        transcript = os.path.join(hp.data, 'transcript.txt')
        lines = codecs.open(transcript, 'r', 'utf-8').readlines()
        for line in lines:
            fname, _, text, _ = line.strip().split("|")

            fpath = os.path.join(hp.data, fname)
            fpaths.append(fpath)

            text += u"␃"  # ␃: EOS
            if hp.num_exp==2:
                text = [j2hcj[char] for char in text]
            elif hp.num_exp==3:
                text = [j2sj[char] for char in text]
            elif hp.num_exp==4:
                text = [j2shcj[char] for char in text]
            text = chain.from_iterable(text)

            text = [char2idx[char] for char in text]
            text_lengths.append(len(text))
            texts.append(np.array(text, np.int32).tostring())

        return fpaths, text_lengths, texts
    else: # synthesize on unseen test text.
        # Parse
        def _normalize(line):
            text = line.split("|")[-1]
            text += u"␃"
            if hp.num_exp==2:
                text = [j2hcj[char] for char in text]
            elif hp.num_exp==3:
                text = [j2sj[char] for char in text]
            elif hp.num_exp==4:
                text = [j2shcj[char] for char in text]
            text = chain.from_iterable(text)
            text = [char2idx[char] for char in text]
            return text

        lines = codecs.open(hp.test_data, 'r', 'utf8').read().splitlines()
        sents = [_normalize(line) for line in lines[1:]]
        texts = np.zeros((len(sents), hp.max_N), np.int32)
        for i, sent in enumerate(sents):
            texts[i, :len(sent)] = sent
        return texts

def get_batch():
    """Loads training data and put them in queues"""
    with tf.device('/cpu:0'):
        # Load data
        fpaths, text_lengths, texts = load_data() # list
        maxlen, minlen = max(text_lengths), min(text_lengths)

        # Calc total batch count
        num_batch = len(fpaths) // hp.B

        # Create Queues
        fpath, text_length, text = tf.train.slice_input_producer([fpaths, text_lengths, texts], shuffle=True)

        # Parse
        text = tf.decode_raw(text, tf.int32)  # (None,)

        def _load_spectrograms(fpath):
            fname = os.path.basename(fpath)
            mel = "/data/private/kss/dc_tts/mels/{}".format(fname.replace("wav", "npy"))
            mag = "/data/private/kss/dc_tts/mags/{}".format(fname.replace("wav", "npy"))
            return fname, np.load(mel), np.load(mag)

        fname, mel, mag = tf.py_func(_load_spectrograms, [fpath], [tf.string, tf.float32, tf.float32])

        # Add shape information
        fname.set_shape(())
        text.set_shape((None,))
        mel.set_shape((None, hp.n_mels))
        mag.set_shape((None, hp.n_fft//2+1))

        # Batching
        _, (texts, mels, mags, fnames) = tf.contrib.training.bucket_by_sequence_length(
                                            input_length=text_length,
                                            tensors=[text, mel, mag, fname],
                                            batch_size=hp.B,
                                            bucket_boundaries=[i for i in range(minlen + 1, maxlen - 1, 20)],
                                            num_threads=8,
                                            capacity=hp.B*4,
                                            dynamic_pad=True)

    return texts, mels, mags, fnames, num_batch

