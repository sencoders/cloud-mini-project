#!/usr/bin/env python3
"""Download only the pinned official base model files; never download a substitute."""
import hashlib
import json
from pathlib import Path
import urllib.request
import yaml

ROOT = Path(__file__).resolve().parents[1]
cfg = yaml.safe_load((ROOT / 'training/config.yaml').read_text())
revision = cfg['model']['revision']
repo = cfg['model']['name']
if repo != 'EleutherAI/pythia-70m':
    raise ValueError('Exactly EleutherAI/pythia-70m is required')
with urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true', timeout=60) as r:
    details = json.load(r)
entries = {f['rfilename']: f for f in details['siblings']}
folder = ROOT / cfg['model']['local_path']
folder.mkdir(parents=True, exist_ok=True)
report = {'repo': repo, 'revision': revision, 'files': {}}
for name in ('config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'model.safetensors'):
    destination = folder / name
    expected = entries[name].get('lfs', {}).get('sha256')
    if not destination.exists():
        temporary = destination.with_suffix(destination.suffix + '.partial')
        print(f'Downloading {repo}@{revision}/{name}', flush=True)
        with urllib.request.urlopen(f'https://huggingface.co/{repo}/resolve/{revision}/{name}', timeout=180) as response, temporary.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temporary.rename(destination)
    actual = hashlib.sha256(destination.read_bytes()).hexdigest()
    if expected and actual != expected:
        raise RuntimeError(f'Hugging Face LFS SHA-256 mismatch: {name}')
    data = destination.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if not expected and blob != entries[name]['blobId']:
        raise RuntimeError(f'Hugging Face Git blob mismatch: {name}')
    report['files'][name] = {'sha256': actual, 'bytes': destination.stat().st_size,
                             'official_lfs_sha256': expected}
(ROOT / 'results/task2/base-download.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
