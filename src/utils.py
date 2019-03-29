import argparse
import json
import logging
import os
import unittest

import numpy as np

import codes
from collections import OrderedDict
import time

decoder_names = ['ML', 'SPA', 'MSA', 'LP', 'ADMM', 'ADMMA']


def setup_parser(code_names, channel_names, decoder_names):
    parser = argparse.ArgumentParser()

    parser.add_argument('channel', help='channel', choices=channel_names)
    parser.add_argument('code', help='code name', choices=code_names)
    parser.add_argument('decoder', help='decoder', choices=decoder_names)

    parser.add_argument('--codeword', help='-1:random from cb, 0:all-zero, 1:all-ones', default=0, type=int,
                        choices=[-1, 0, 1])
    parser.add_argument('--min-wec', help='min word errors to accumulate', default=100, type=int)
    parser.add_argument('--params', nargs='+', type=float, default=[.1, .01])

    parser.add_argument('--max-iter', help='max iterations in iterative decoders', default=10, type=int)
    parser.add_argument('--mu', help='mu', default=3., type=float)
    parser.add_argument('--eps', help='epsilon', default=1e-5, type=float)

    parser.add_argument('--log-freq', help='log frequency in seconds', default=5., type=float)
    return bind_parser_common(parser)


def bind_parser_common(parser):
    parser.add_argument('--data-dir', help='data directory', default=os.path.join('.', 'data'))
    parser.add_argument('--plots-dir', help='save location', default=os.path.join('.', 'plots'))
    parser.add_argument('--debug', help='logs debug info', action='store_true')
    parser.add_argument('--console', help='prints log onto console', action='store_true')
    return parser


def setup_console_logger(level=logging.DEBUG):
    logging.basicConfig(format='%(name)s|%(message)s', level=level)


def setup_file_logger(path, name, level=logging.DEBUG):
    logging.basicConfig(filename=os.path.join(path, '%s.log' % name),
                        filemode='a',
                        format='%(asctime)s,%(msecs)03d|%(name)s|%(levelname)s|%(message)s',
                        datefmt='%H:%M:%S',
                        level=level)
    logging.info('Logger init to file. %s' % ('%' * 80))


class TestCase(unittest.TestCase):
    def sample(self, code, param, decoders, x, y, **kwargs):
        x_, y_ = np.array(x), np.array(y)
        for decoder in decoders:
            dec = decoder(param, codes.get_code(code), **kwargs)
            # print(dec, x_, dec.decode(y_))
            self.assertTrue((dec.decode(y_) == x_).all())
            # spa = SPA(param, codes.get_code(code))
            # self.assertTrue((spa.decode(y_) == x_).all())


def get_data_file_list(data_dir):
    return tuple(it for it in next(os.walk(data_dir), ((), (), ()))[2]
                 if os.path.splitext(it)[1] == '.json')


def load_json(file_path):
    try:
        ff = open(file_path, 'r')
        data = json.load(ff, object_pairs_hook=OrderedDict)
        ff.close()
    except:
        data = None
        # print('Error loading: %s' % file_path)
    finally:
        return data


def make_dir_if_not_exists(dir_path):
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


class Saver:
    def __init__(self, data_dir, run_ids):
        self.dict = OrderedDict(run_ids)
        make_dir_if_not_exists(data_dir)
        dir_path, file_name = data_dir, '-'.join(self.dict.values())
        self.file_path = os.path.join(dir_path, '%s.json' % file_name)

    def add_meta(self, key, val):
        self.dict[key] = val

    def add(self, param, val_dict):
        data = load_json(self.file_path)
        if data is None:
            data = OrderedDict()
            for key in self.dict: data[key] = self.dict[key]
            for key in val_dict: data[key] = {}

        for key in val_dict: data[key][str(param)] = float(val_dict[key])
        self.write_(data)

    def write_(self, data):
        with open(self.file_path, 'w') as fp:
            json.dump(data, fp, indent=4)

    def add_all(self, val_dict):
        z = self.dict.copy()
        z.update(val_dict)
        self.write_(z)

    def add_deprecated(self, run_id, val):
        data = self.load({})
        temp = data
        for key in run_id[0:-1]:
            if key not in temp.keys(): temp[key] = {}
            temp = temp[key]
        temp[run_id[-1]] = val

        with open(self.file_path, 'w') as ff:
            json.dump(data, ff)


class LoopProfiler:
    class Tag:
        def __init__(self, name, line, prof):
            self.name, self.line, self.prof = name, line, prof

        def elapsed(self):
            return (time.time() - self.updated) * 1000

        def __enter__(self):
            self.updated = time.time()
            extra = '' if self.line is None else ': ' + self.line
            self.prof.log.debug("(( '" + self.name + "'" + extra)
            return self

        def __exit__(self, type, value, traceback):
            elapsed = self.elapsed()
            self.prof.log.debug('    elapsed[%s] ))' % str(int(elapsed)))
            self.prof.tags[self.name] = self.prof.tags.get(self.name, 0) + elapsed

    def __init__(self, log, dump_freq):
        self.log = log
        self.updated = time.time()
        self.dump_freq = dump_freq
        self.tags = OrderedDict()
        self.step_count = 0

    def __enter__(self):
        return self

    def start(self, line=None):
        self.step_count += 1
        if line is not None: self.log.debug(line)
        return self

    def tag(self, name, line=None):
        return LoopProfiler.Tag(name, line, self)

    def __exit__(self, typ, value, traceback):
        if self.dump_freq > 0 and self.step_count % self.dump_freq == 0:
            summary = ', '.join(["'%s':%d" % (key, int(val)) for key, val in self.tags.items()])
            self.log.info('Summary at[%d] for[%d]: [' % (self.step_count, self.dump_freq) + summary + ']')
            for key in self.tags: self.tags[key] = 0