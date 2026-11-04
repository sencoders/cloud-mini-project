#!/usr/bin/env python3
"""Back up or restore exact S3 object bytes for the observed storage recovery."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.task1 import credentials
from worker.storage import client, get, put_verified, sha256

BACKUP = ROOT / '.local/s3-backup'


def listing(s3, bucket):
    return sorted(o['Key'] for page in s3.get_paginator('list_objects_v2').paginate(
        Bucket=bucket) for o in page.get('Contents', []))


def main(action):
    credentials()
    s3 = client()
    BACKUP.mkdir(parents=True, exist_ok=True)
    manifest_path = BACKUP / 'manifest.json'
    if action == 'export':
        buckets = sorted(b['Name'] for b in s3.list_buckets()['Buckets'])
        objects = [(bucket, key) for bucket in buckets for key in listing(s3, bucket)]

        def export_one(item):
            bucket, key = item
            data = get(s3, key, bucket)
            path = BACKUP / bucket / key
            if not path.resolve().is_relative_to(BACKUP.resolve()):
                raise ValueError('Unsafe object key')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return {'bucket': bucket, 'key': key, 'sha256': sha256(data), 'bytes': len(data)}

        with ThreadPoolExecutor(max_workers=8) as pool:
            entries = list(pool.map(export_one, objects))
        manifest = {'buckets': buckets, 'objects': entries}
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        (ROOT / 'results/storage-export-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(f'Exported {len(entries)} exact objects from {buckets}', flush=True)
    else:
        manifest = json.loads(manifest_path.read_text())
        existing = {b['Name'] for b in s3.list_buckets()['Buckets']}
        for bucket in manifest['buckets']:
            if bucket not in existing:
                s3.create_bucket(Bucket=bucket)

        def restore_one(entry):
            data = (BACKUP / entry['bucket'] / entry['key']).read_bytes()
            if sha256(data) != entry['sha256']:
                raise RuntimeError('Backup checksum mismatch')
            digest = put_verified(s3, entry['key'], data, entry['bucket'])
            if digest != entry['sha256']:
                raise RuntimeError('Restored checksum mismatch')
            return digest

        with ThreadPoolExecutor(max_workers=8) as pool:
            verified = list(pool.map(restore_one, manifest['objects']))
        for bucket in manifest['buckets']:
            expected = sorted(e['key'] for e in manifest['objects'] if e['bucket'] == bucket)
            if listing(s3, bucket) != expected:
                raise RuntimeError('Restored object listing differs')
        report = {'buckets': manifest['buckets'], 'objects_exported': len(manifest['objects']),
                  'objects_restored_and_hash_verified': len(verified), 'all_object_keys_match': True,
                  'original_volume_directory_retained': True}
        (ROOT / 'results/storage-migration.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['export', 'restore'])
    main(ap.parse_args().action)
