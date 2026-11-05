import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random

import numpy as np
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'training/config.yaml'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_config():
    cfg = yaml.safe_load(CONFIG.read_text())
    if cfg['model']['name'] != 'EleutherAI/pythia-70m':
        raise ValueError('The assignment requires exactly EleutherAI/pythia-70m')
    if cfg['training']['device'] != 'cpu' or cfg['training']['dtype'] != 'float32':
        raise ValueError('Only float32 CPU training is supported')
    if cfg['training']['max_examples'] != 1500:
        raise ValueError('The training pool must be exactly the first 1500 records')
    for name, expected in cfg['libraries'].items():
        actual = importlib.metadata.version(name)
        allowed = {str(expected)}
        if name == 'torch':
            # The official Linux CPU wheel has this build suffix; reject CUDA
            # variants and all differing upstream versions.
            allowed.add(str(expected) + '+cpu')
        if actual not in allowed:
            raise RuntimeError(f'{name}: expected {sorted(allowed)}, installed {actual}')
    return cfg


def setup_cpu(cfg):
    seed = cfg['training']['seed']
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(cfg['training']['cpu_threads'])
    torch.set_num_interop_threads(cfg['training']['interop_threads'])
    torch.use_deterministic_algorithms(True)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def local_credentials():
    # Read existing credentials only; Task 2 never creates or rotates storage secrets.
    path = ROOT / '.local/credentials.json'
    if not (os.environ.get('AWS_ACCESS_KEY_ID') and os.environ.get('AWS_SECRET_ACCESS_KEY')):
        os.environ.update(json.loads(path.read_text()))
    os.environ.setdefault('S3_ENDPOINT', 'http://127.0.0.1:8333')
