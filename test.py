# %load evaluate_eer.py
# Copyright (c) 2021 PaddlePaddle Authors. All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import os

import numpy as np
import paddle
import paddle.nn as nn
import paddle.nn.functional as F
import paddleaudio
import yaml
from paddleaudio.transforms import *
from paddleaudio.utils import get_logger

import metrics
from dataset import get_val_loader
from models import ECAPA_TDNN, ResNetSE34, ResNetSE34V2

logger = get_logger()

file2feature = {}


class Normalize:
    def __init__(self, eps=1e-8):
        self.eps = eps

    def __call__(self, x):
        assert x.ndim == 3
        mean = paddle.mean(x, [1, 2], keepdim=True)
        std = paddle.std(x, [1, 2], keepdim=True)
        return (x - mean) / (std + self.eps)


def get_feature(file, model, melspectrogram):
    global file2feature
    if file in file2feature:
        return file2feature[file]
    s, _ = paddleaudio.load(file, sr=16000)
    s = paddle.to_tensor(s[None, :])
    s = melspectrogram(s).astype('float32')
    #import pdb;pdb.set_trace()
    #s = s[:,:,:400]
    with paddle.no_grad():
        feature = model(s).squeeze()
    feature = feature / paddle.sqrt(paddle.sum(feature**2))
    file2feature.update({file: feature})
    return feature


class Normalize2:
    def __init__(self, mean_file, eps=1e-5):
        self.eps = eps
        mean = paddle.load(mean_file)['mean']
        std = paddle.load(mean_file)['std']

        self.mean = mean.unsqueeze((0, 2))
        #self.std = std.unsqueeze((0,2))+eps

    def __call__(self, x):
        assert x.ndim == 3
        return x - self.mean


def compute_eer(config, model):

    transforms = []
    melspectrogram = LogMelSpectrogram(**config['fbank'])
    transforms += [melspectrogram]
    if config['normalize']:
        transforms += [Normalize2(config['mean_std_file'])]

    transforms = Compose(transforms)

    global file2feature
    file2feature = {}
    test_list = config['test_list']
    test_folder = config['test_folder']
    model.eval()
    with open(test_list) as f:
        lines = f.read().split('\n')
    label_wav_pairs = [l.split() for l in lines if len(l) > 0]
    logger.info(f'{len(label_wav_pairs)} test pairs listed')
    labels = []
    scores = []
    for i, (label, f1, f2) in enumerate(label_wav_pairs):
        full_path1 = os.path.join(test_folder, f1)
        full_path2 = os.path.join(test_folder, f2)
        feature1 = get_feature(full_path1, model, transforms)
        feature2 = get_feature(full_path2, model, transforms)
        score = float(paddle.dot(feature1.squeeze(), feature2.squeeze()))
        labels.append(label)
        scores.append(score)
        if i % (len(label_wav_pairs) // 10) == 0:
            logger.info(f'processed {i}|{len(label_wav_pairs)}')

    scores = np.array(scores)
    labels = np.array([int(l) for l in labels])
    result = metrics.compute_eer(scores, labels)
    min_dcf = metrics.compute_min_dcf(result.fr, result.fa)
    logger.info(f'eer={result.eer}, thresh={result.thresh}, minDCF={min_dcf}')
    return result, min_dcf


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('-c',
                        '--config',
                        type=str,
                        required=False,
                        default='config.yaml')
    parser.add_argument(
        '-d',
        '--device',
        #choices=['cpu', 'gpu'],
        default="gpu",
        help="Select which device to train model, defaults to gpu.")
    parser.add_argument('-w', '--weight', type=str, required=True)
    # parser.add_argument('--test_list', type=str, required=True)
    # parser.add_argument('--test_folder', type=str, required=True)
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)
    paddle.set_device(args.device)
    logger.info('model:' + config['model']['name'])
    logger.info('device: ' + args.device)

    logger.info(f'using ' + config['model']['name'])
    ModelClass = eval(config['model']['name'])
    model = ModelClass(**config['model']['params'])
    state_dict = paddle.load(args.weight)
    if 'model' in state_dict.keys():
        state_dict = state_dict['model']

    model.load_dict(state_dict)
    # model.train()
    result, min_dcf = compute_eer(config, model)
    logger.info(f'eer={result.eer}, thresh={result.thresh}, minDCF={min_dcf}')
