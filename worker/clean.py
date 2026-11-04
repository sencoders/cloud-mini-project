"""Reject invalid teacher records, deduplicate commands, publish verified data."""
import argparse
import json
from pathlib import Path

from worker.label import encode, load_pool, shard
from worker.storage import client, get, put_verified, sha256

KEYS = {'intent', 'date', 'time', 'place'}
INTENTS = {'alarm_set', 'alarm_query', 'calendar_set', 'calendar_query',
           'calendar_remove', 'weather_query', 'datetime_query', 'recommendation_events'}


def strict_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('Duplicate JSON key')
        obj[key] = value
    return obj


def reject_constant(value):
    raise ValueError(f'Non-JSON constant: {value}')


def rejection(record):
    try:
        if not isinstance(record['teacher_raw'], str):
            return 'a_invalid_json'
        value = json.loads(record['teacher_raw'], object_pairs_hook=strict_object,
                           parse_constant=reject_constant)
    except (ValueError, TypeError):
        return 'a_invalid_json'
    if not isinstance(value, dict) or set(value) != KEYS:
        return 'b_wrong_keys'
    if not isinstance(value['intent'], str) or value['intent'] not in INTENTS:
        return 'c_invalid_intent'
    if any(v is not None and (not isinstance(v, str) or v not in record['text'])
           for v in (value[k] for k in ('date', 'time', 'place'))):
        return 'd_invalid_slot'
    return None


def clean(records):
    counts = dict.fromkeys(('input', 'a_invalid_json', 'b_wrong_keys', 'c_invalid_intent',
                           'd_invalid_slot', 'duplicates', 'kept'), 0)
    counts['input'] = len(records)
    kept, seen, rejected = [], set(), []
    for record in sorted(records, key=lambda r: r['id']):
        reason = rejection(record)
        if reason:
            counts[reason] += 1
            rejected.append({'id': record['id'], 'reason': reason})
        elif record['text'] in seen:
            counts['duplicates'] += 1
            rejected.append({'id': record['id'], 'reason': 'duplicates'})
        else:
            seen.add(record['text'])
            # Preserve teacher_raw exactly as the training target, not a repaired JSON.
            kept.append(record)
    counts['kept'] = len(kept)
    assert counts['input'] == sum(v for k, v in counts.items() if k != 'input')
    return b''.join(encode(r) for r in kept), counts, rejected


def collect(s3, rows, prefix, count):
    records = []
    for index in range(count):
        raw = get(s3, f'{prefix}/shard-{index}.jsonl')
        part = [json.loads(line) for line in raw.decode().splitlines()]
        expected = {r['id']: r['text'] for r in shard(rows, index, count)}
        actual = [r['id'] for r in part]
        if len(actual) != len(set(actual)) or set(actual) != set(expected):
            raise ValueError(f'Shard {index}: missing, duplicated, or misplaced IDs')
        for r in part:
            if set(r) != {'id', 'text', 'teacher_raw'} or r['text'] != expected[r['id']]:
                raise ValueError(f'Shard {index}: corrupted source record')
        records.extend(part)
    return records


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prefix', default='teacher')
    ap.add_argument('--shard-count', type=int, default=2)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--output', default='v1')
    ap.add_argument('--results', default='results/full')
    args = ap.parse_args()
    if args.shard_count < 1 or args.limit < 0:
        ap.error('Invalid shard count or limit')
    s3 = client()
    rows = load_pool(get(s3, 'commands_pool.jsonl'))
    if args.limit:
        rows = rows[:args.limit]
    records = collect(s3, rows, args.prefix, args.shard_count)
    data, counts, rejected = clean(records)
    digest = put_verified(s3, f'{args.output}/train.jsonl', data)
    checksum = f'{digest}  train.jsonl\n'.encode()
    put_verified(s3, f'{args.output}/train.sha256', checksum)
    # Download both objects independently and verify against the published checksum.
    if sha256(get(s3, f'{args.output}/train.jsonl')) != get(
            s3, f'{args.output}/train.sha256').decode().split()[0]:
        raise RuntimeError('Published checksum verification failed')
    report = {**counts, 'sha256': digest, 'source_prefix': args.prefix,
              'all_ids_accounted_for': len(records) == len(rows)}
    out = Path(args.results)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'train.jsonl').write_bytes(data)
    (out / 'train.sha256').write_bytes(checksum)
    (out / 'counts.json').write_bytes(encode(report))
    (out / 'rejections.jsonl').write_bytes(b''.join(encode(r) for r in rejected))
    for index in range(args.shard_count):
        (out / f'shard-{index}.jsonl').write_bytes(get(s3, f'{args.prefix}/shard-{index}.jsonl'))
    put_verified(s3, f'{args.output}/counts.json', encode(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
