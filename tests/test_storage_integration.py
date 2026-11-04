"""Opt-in live SeaweedFS test; creates and deletes only an isolated temporary key."""
import os
import uuid

import pytest

from worker.storage import client, get, maybe_get, put_verified


@pytest.mark.skipif(os.environ.get('TASK1_S3_TEST') != '1', reason='Opt-in live local S3 test')
def test_live_seaweedfs_roundtrip_and_overwrite():
    from scripts.task1 import credentials
    credentials()
    s3 = client()
    assert {'datasets', 'models'} <= {b['Name'] for b in s3.list_buckets()['Buckets']}
    key = '_integration-tests/' + uuid.uuid4().hex
    try:
        assert maybe_get(s3, key) is None
        digest = put_verified(s3, key, b'first\n')
        assert s3.head_object(Bucket='datasets', Key=key)['Metadata']['sha256'] == digest
        put_verified(s3, key, b'second\n')
        assert get(s3, key) == b'second\n'
    finally:
        s3.delete_object(Bucket='datasets', Key=key)
    assert maybe_get(s3, key) is None
