"""S3 operations with byte-for-byte read-back verification."""
import hashlib
import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def client():
    return boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT'],
                        region_name='us-east-1', config=Config(
                            signature_version='s3v4', s3={'addressing_style': 'path'},
                            connect_timeout=10, read_timeout=60,
                            retries={'max_attempts': 5, 'mode': 'standard'},
                            request_checksum_calculation='when_required',
                            response_checksum_validation='when_required'))


def get(s3, key, bucket='datasets'):
    return s3.get_object(Bucket=bucket, Key=key)['Body'].read()


def maybe_get(s3, key):
    try:
        return get(s3, key)
    except ClientError as exc:
        if exc.response['Error']['Code'] in ('NoSuchKey', '404'):
            return None
        raise


def put_verified(s3, key, data, bucket='datasets'):
    digest = sha256(data)
    s3.put_object(Bucket=bucket, Key=key, Body=data, Metadata={'sha256': digest})
    actual = get(s3, key, bucket)
    if actual != data:
        raise RuntimeError(f'S3 read-back mismatch: {bucket}/{key}')
    return digest


def keys(s3, prefix):
    return [o['Key'] for page in s3.get_paginator('list_objects_v2').paginate(
        Bucket='datasets', Prefix=prefix) for o in page.get('Contents', [])]
