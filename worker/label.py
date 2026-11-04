"""One deterministic shard, resumable from verified per-ID S3 checkpoints."""
import json
import os
import time
import urllib.request
from pathlib import Path

from worker.storage import client, get, maybe_get, put_verified, sha256


def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


def load_pool(data):
    # Physical line numbering is authoritative; blank lines are an input error.
    rows = [json.loads(line) for line in data.decode().splitlines()]
    ids = [r['id'] for r in rows]
    if len(ids) != len(set(ids)) or any(
            set(r) != {'id', 'text'} or not isinstance(r['id'], str)
            or not isinstance(r['text'], str) for r in rows):
        raise ValueError('Pool requires unique string IDs and text, with no blank lines')
    return rows


def shard(rows, index, count):
    if count < 1 or not 0 <= index < count:
        raise ValueError('Require SHARD_COUNT > 0 and 0 <= SHARD_INDEX < SHARD_COUNT')
    return [row for n, row in enumerate(rows) if n % count == index]


def teacher(text, prompt):
    payload = {'model': 'phi3.5:latest', 'stream': False, 'format': 'json',
               'prompt': prompt + '\nCommand: ' + json.dumps(text, ensure_ascii=False) + '\nJSON:',
               'options': {'temperature': 0, 'seed': 42, 'num_predict': 256, 'num_ctx': 2048},
               'keep_alive': '24h'}
    req = urllib.request.Request(os.environ['OLLAMA_URL'].rstrip('/') + '/api/generate',
                                 data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as response:
        result = json.load(response)
    if result.get('done') is not True or not isinstance(result.get('response'), str):
        raise ValueError('Incomplete or missing Ollama response')
    # Do not strip fences, whitespace, or repair/truncate the generated response.
    return result['response']


def log(event, **fields):
    print(json.dumps({'time': time.time(), 'event': event, **fields}), flush=True)


def run(s3, rows, prompt, index, count, prefix, generate=teacher):
    assigned = shard(rows, index, count)
    manifest = encode({'pool_sha256': sha256(b''.join(encode(r) for r in rows)),
                       'prompt_sha256': sha256(prompt.encode()), 'shard_count': count,
                       'model': 'phi3.5:latest', 'temperature': 0, 'seed': 42,
                       'num_predict': 256, 'num_ctx': 2048, 'format': 'json'})
    manifest_key = f'{prefix}/progress/shard-{index}/manifest.json'
    old = maybe_get(s3, manifest_key)
    if old is not None and old != manifest:
        raise ValueError('Run configuration changed; use a new output prefix')
    put_verified(s3, manifest_key, manifest)
    records = []
    log('start', shard_index=index, shard_count=count, assigned=len(assigned))
    for row in assigned:
        key = f'{prefix}/progress/shard-{index}/{row["id"]}.json'
        checkpoint = maybe_get(s3, key)
        if checkpoint is not None:
            record = json.loads(checkpoint)
            if set(record) != {'id', 'text', 'teacher_raw'} or any(
                    record[k] != row[k] for k in ('id', 'text')) or not isinstance(record['teacher_raw'], str):
                raise ValueError(f'Invalid checkpoint: {key}')
            log('resume', id=row['id'], shard_index=index)
        else:
            for attempt in range(1, 6):
                try:
                    raw = generate(row['text'], prompt)
                    break
                except Exception as exc:
                    log('teacher_retry', id=row['id'], attempt=attempt, error=str(exc))
                    if attempt == 5:
                        raise
                    time.sleep(min(2 ** attempt, 30))
            record = {**row, 'teacher_raw': raw}
            # A storage failure stops this process; no ID is silently skipped.
            put_verified(s3, key, encode(record))
            log('labelled', id=row['id'], shard_index=index)
        records.append(record)
        # Publish complete progress after each durable checkpoint. A restart rebuilds
        # this object from checkpoints; the cleaner requires ALL expected IDs.
        put_verified(s3, f'{prefix}/shard-{index}.jsonl', b''.join(encode(r) for r in records))
    log('complete', shard_index=index, records=len(records))
    return records


def main():
    s3 = client()
    rows = load_pool(get(s3, 'commands_pool.jsonl'))
    limit = int(os.environ.get('LIMIT', '0'))
    if limit:
        if limit < 1:
            raise ValueError('LIMIT must be positive')
        rows = rows[:limit]
    run(s3, rows, Path('prompts/teacher_prompt.txt').read_text(),
        int(os.environ['SHARD_INDEX']), int(os.environ['SHARD_COUNT']), os.environ['OUTPUT_PREFIX'])


if __name__ == '__main__':
    main()
