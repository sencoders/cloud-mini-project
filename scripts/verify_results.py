#!/usr/bin/env python3
"""Offline verification of exported raw shards, ID coverage, cleaning, and checksum."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from worker.clean import clean
from worker.label import load_pool
from worker.storage import sha256


def verify(directory, limit=0):
    source = load_pool((ROOT / 'data/commands_pool.jsonl').read_bytes())
    if limit:
        source = source[:limit]
    records = []
    shard_sizes = []
    for i in range(2):
        part = [json.loads(line) for line in (directory / f'shard-{i}.jsonl').read_bytes().splitlines()]
        expected = {r['id']: r['text'] for n, r in enumerate(source) if n % 2 == i}
        ids = [r['id'] for r in part]
        if len(ids) != len(set(ids)) or set(ids) != set(expected):
            raise ValueError(f'Shard {i}: missing, duplicated or misplaced IDs')
        if any(r['text'] != expected[r['id']] for r in part):
            raise ValueError('Source text changed')
        records.extend(part)
        shard_sizes.append(len(part))
    regenerated, counts, _ = clean(records)
    saved = (directory / 'train.jsonl').read_bytes()
    checksum = (directory / 'train.sha256').read_text().strip()
    if saved != regenerated or checksum != f'{sha256(saved)}  train.jsonl':
        raise ValueError('Saved dataset or checksum differs from independent cleaning')
    reported = json.loads((directory / 'counts.json').read_text())
    if any(reported[k] != v for k, v in counts.items()) or reported['sha256'] != sha256(saved):
        raise ValueError('Reported counts or digest differ')
    report = {'source_records': len(source), 'shard_records': shard_sizes,
              'unique_raw_ids': len({r['id'] for r in records}),
              'missing_ids': 0, 'repeated_ids': 0, 'source_texts_match': True,
              'regenerated_bytes_match': True, 'sha256': sha256(saved),
              'counts_match': True}
    (directory / 'offline-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--results', type=Path, default=ROOT / 'results/full')
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()
    verify(args.results, args.limit)
