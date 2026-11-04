"""Read-only S3 model download, bounded-memory hashing, Secret credentials only."""
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

import boto3
from botocore.config import Config


def file_sha256(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as file:
        while chunk := file.read(1024 * 1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def model_location(uri):
    parsed = urlsplit(uri)
    if parsed.scheme != 's3' or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError('MODEL_URI must be s3://bucket/prefix/')
    prefix = parsed.path.strip('/')
    if not prefix or any(p in ('.', '..') for p in prefix.split('/')):
        raise ValueError('Unsafe model prefix')
    return parsed.netloc, prefix


def secret_client(endpoint):
    # No default AWS credential chain or host credentials file is allowed here.
    access = os.environ['AWS_ACCESS_KEY_ID']
    secret = os.environ['AWS_SECRET_ACCESS_KEY']
    if not access or not secret:
        raise ValueError('Empty Secret credentials')
    return boto3.client('s3', endpoint_url=endpoint, aws_access_key_id=access,
            aws_secret_access_key=secret, region_name='us-east-1', config=Config(
                signature_version='s3v4', s3={'addressing_style': 'path'},
                connect_timeout=10, read_timeout=60,
                retries={'max_attempts': 5, 'mode': 'standard'},
                request_checksum_calculation='when_required',
                response_checksum_validation='when_required'))


def parse_manifest(raw):
    entries = []
    for line in raw.decode('utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        if not match or match[2] in ('.', '..', 'model.sha256'):
            raise ValueError('Invalid artifact checksum manifest')
        entries.append((match[1], match[2]))
    names = [name for _, name in entries]
    required = {'model.safetensors', 'config.json', 'tokenizer.json',
                'tokenizer_config.json', 'version.json'}
    if len(names) != len(set(names)) or not required <= set(names):
        raise ValueError('Incomplete or repeated manifest entries')
    return entries


def download_model(settings, directory, emit, s3=None):
    s3 = s3 or secret_client(settings.s3_endpoint)
    bucket, prefix = model_location(settings.model_uri)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    emit('model_download_start', model_uri=settings.model_uri)
    body = s3.get_object(Bucket=bucket, Key=prefix + '/model.sha256')['Body']
    try:
        manifest = body.read(65537)
    finally:
        body.close()
    if len(manifest) > 65536:
        raise ValueError('Model manifest is too large')
    entries = parse_manifest(manifest)
    for expected, name in entries:
        target = directory / name
        temporary = directory / (name + '.partial')
        body = s3.get_object(Bucket=bucket, Key=f'{prefix}/{name}')['Body']
        try:
            with temporary.open('wb') as output:
                for chunk in body.iter_chunks(chunk_size=1024 * 1024):
                    output.write(chunk)
        finally:
            body.close()
        if file_sha256(temporary) != expected:
            raise ValueError(f'Artifact checksum mismatch: {name}')
        temporary.rename(target)
        emit('model_file_verified', file=name, bytes=target.stat().st_size, sha256=expected)
    (directory / 'model.sha256').write_bytes(manifest)
    metadata = json.loads((directory / 'version.json').read_text())
    if (metadata.get('version') != settings.model_version or metadata.get('smoke') is not False
            or metadata.get('status') != 'complete'
            or metadata.get('model_name') != 'EleutherAI/pythia-70m'):
        raise ValueError('Model version/provenance does not match MODEL_VERSION')
    emit('model_download_complete', files=len(entries), manifest_sha256=hashlib.sha256(manifest).hexdigest())
    return directory
