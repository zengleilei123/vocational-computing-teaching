"""A learn-by-example, binary-pixel k-NN classifier, not a neural network.

Training here means retaining labeled examples. Distance is normalized Hamming
(squared Euclidean for binary pixels). Votes are not calibrated probabilities.
"""
from collections import Counter

LABELS = ('up', 'right', 'down', 'left')
_UP = [0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0]


def rotate(pixels):
    return [pixels[(4 - c) * 5 + r] for r in range(5) for c in range(5)]


DEMO_TRAIN = []
_shape = _UP
for _label in LABELS:
    DEMO_TRAIN.append({'label': _label, 'pixels': list(_shape)})
    _shape = rotate(_shape)


def pixels(value):
    if not isinstance(value, list) or len(value) != 25 or any(type(x) is not int or x not in (0, 1) for x in value):
        raise ValueError('图像必须是 25 个 0/1 整数。')
    return value


def samples(value, name):
    if not isinstance(value, list) or not 1 <= len(value) <= 160:
        raise ValueError(f'{name}需要 1–160 个样本。')
    seen = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {'label', 'pixels'} or item['label'] not in LABELS:
            raise ValueError('样本仅包含 label 和 pixels；标签为 up/right/down/left。')
        key = tuple(pixels(item['pixels']))
        if sum(key) == 0:
            raise ValueError('空白画板不能作为样本。')
        if key in seen:
            raise ValueError('同一集合有重复图像或冲突标签，请保留独立样本。')
        seen.add(key)
    return seen


def training(train, k):
    keys = samples(train, '训练集')
    if {s['label'] for s in train} != set(LABELS):
        raise ValueError('请为上、右、下、左四个方向各收集至少一个训练样本。')
    if type(k) is not int or k not in (1, 3, 5) or k > len(train):
        raise ValueError('k 必须是 1/3/5 且不超过训练样本数量。')
    return keys


def _predict(train, image, k):
    if not any(image):
        return {'label': None, 'reason': 'blank', 'distance': None, 'vote_share': 0}
    ranked = sorted((sum(a != b for a, b in zip(s['pixels'], image)) / 25, s['label']) for s in train)
    votes = Counter(label for _, label in ranked[:k])
    leaders = sorted(votes, key=lambda label: (-votes[label], label))
    distance = ranked[0][0]
    if distance > 0.32:
        label, reason = None, 'too_far'
    elif len(leaders) > 1 and votes[leaders[0]] == votes[leaders[1]]:
        label, reason = None, 'tied_vote'
    elif k == 1 and any(d == distance and label != ranked[0][1] for d, label in ranked[1:]):
        label, reason = None, 'tied_distance'
    else:
        label, reason = leaders[0], 'matched'
    return {'label': label, 'reason': reason, 'distance': distance,
            'vote_share': votes[leaders[0]] / k}


def classify(train, image, k=1):
    training(train, k)
    return _predict(train, pixels(image), k)


def evaluate(train, test, k=1):
    keys = training(train, k)
    test_keys = samples(test, '测试集')
    if keys & test_keys:
        raise ValueError('测试图像与训练集重合，不能用作独立评测。请重新绘制留出样本。')
    confusion = {label: {pred: 0 for pred in (*LABELS, 'unknown')} for label in LABELS}
    results, correct, covered = [], 0, 0
    for sample in test:
        prediction = _predict(train, sample['pixels'], k)
        label = prediction['label']
        confusion[sample['label']][label or 'unknown'] += 1
        correct += label == sample['label']
        covered += label is not None
        results.append({'expected': sample['label'], **prediction})
    return {'n_test': len(test), 'accuracy': correct / len(test), 'coverage': covered / len(test),
            'confusion': confusion, 'results': results,
            'warning': '仅反映当前小型留出集；票数比例不是概率，不能推断真实场景效果。'}
