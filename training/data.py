"""Verified first-1500 selection and completion-only causal language-model labels."""
import json
from pathlib import Path

import torch

from training.common import ROOT, digest, local_credentials, write_json
from worker.clean import rejection
from worker.storage import client, get


def select_records(raw, checksum, expected, limit):
    if digest(raw) != checksum.split()[0] or digest(raw) != expected:
        raise ValueError('Task 1 dataset checksum mismatch')
    rows = [json.loads(line) for line in raw.splitlines()]
    ids = [r['id'] for r in rows]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise ValueError('Dataset must already be in unique ID order')
    if not 1 <= limit <= 1500 or len(rows) < 1500:
        raise ValueError('Require 1..1500 examples from a full cleaned dataset')
    if any(set(r) != {'id', 'text', 'teacher_raw'} or not r['id'].startswith('C')
           or rejection(r) is not None for r in rows):
        raise ValueError('Unexpected Task 1 schema or invalid teacher target')
    return rows[:limit]


def download_records(cfg, limit, evidence):
    local_credentials()
    s3 = client()
    spec = cfg['data']
    raw = get(s3, spec['key'], spec['bucket'])
    checksum = get(s3, spec['checksum_key'], spec['bucket']).decode()
    rows = select_records(raw, checksum, spec['expected_sha256'], limit)
    path = ROOT / spec['cache_path']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    selected_bytes = b'\n'.join(raw.splitlines()[:limit]) + b'\n'
    info = {'source_uri': f"s3://{spec['bucket']}/{spec['key']}",
            'dataset_sha256': digest(raw), 'selected_source_sha256': digest(selected_bytes),
            'records_available': len(raw.splitlines()), 'records_selected': len(rows),
            'ids': [r['id'] for r in rows],
            'teacher_targets_sha256': digest(json.dumps([r['teacher_raw'] for r in rows],
                                                        ensure_ascii=False).encode()),
            'target_field': 'teacher_raw', 'validation_used': False}
    write_json(Path(evidence) / 'data-verification.json', info)
    return rows, info


def command_prompt(text):
    return f'Command: {text}\nJSON:'


def encode_example(row, tokenizer, max_length):
    prompt = command_prompt(row['text'])
    # The one separator space is part of the assignment's format. The teacher's
    # target string is never parsed, normalized, reconstructed or substituted.
    full = prompt + ' ' + row['teacher_raw']
    encoded = tokenizer(full, add_special_tokens=False, return_offsets_mapping=True)
    ids = list(encoded['input_ids']) + [tokenizer.eos_token_id]
    labels = [token if start >= len(prompt) else -100
              for token, (start, end) in zip(encoded['input_ids'], encoded['offset_mapping'])]
    labels.append(tokenizer.eos_token_id)
    if len(ids) > max_length:
        raise ValueError(f"{row['id']}: {len(ids)} tokens exceeds {max_length}; refusing target truncation")
    if not any(t != -100 for t in labels[:-1]):
        raise ValueError('No supervised completion tokens')
    return {'input_ids': ids, 'labels': labels}


class CompletionCollator:
    def __init__(self, pad_token_id):
        self.pad_token_id = pad_token_id

    def __call__(self, items):
        length = max(len(item['input_ids']) for item in items)
        ids, labels, masks = [], [], []
        for item in items:
            n = len(item['input_ids'])
            ids.append(item['input_ids'] + [self.pad_token_id] * (length - n))
            labels.append(item['labels'] + [-100] * (length - n))
            masks.append([1] * n + [0] * (length - n))
        return {k: torch.tensor(v, dtype=torch.long, device='cpu')
                for k, v in {'input_ids': ids, 'labels': labels, 'attention_mask': masks}.items()}
