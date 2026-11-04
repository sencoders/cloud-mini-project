"""Checksum, S3 verification, and deterministic GitHub Release packaging."""
import argparse
import gzip
import io
import json
from pathlib import Path
import tarfile

from training.common import ROOT, digest, local_credentials, read_config, write_json
from worker.storage import client, get, put_verified


def manifest(directory):
    files = sorted(p for p in directory.iterdir() if p.is_file() and p.name != 'model.sha256')
    if not (directory / 'model.safetensors').is_file():
        raise ValueError('Missing model.safetensors')
    return ''.join(f'{digest(p.read_bytes())}  {p.name}\n' for p in files).encode()


def verify_directory(directory):
    checksum = directory / 'model.sha256'
    actual = manifest(directory)
    if checksum.read_bytes() != actual:
        raise ValueError('Artifact checksum mismatch')
    return actual


def source_directory(cfg, version):
    if version not in cfg['versions']:
        raise ValueError('Unknown model version')
    directory = ROOT / cfg['artifacts']['local_root'] / version
    info = json.loads((directory / 'version.json').read_text())
    if info['status'] != 'complete' or info['smoke'] or info['subset'] != 1500:
        raise ValueError('Only complete full-run artifacts may be published')
    if info['version'] != version or info['model_name'] != cfg['model']['name']:
        raise ValueError('Artifact provenance mismatch')
    return directory


def prepare(directory):
    checksum = directory / 'model.sha256'
    if checksum.exists():
        verify_directory(directory)
    else:
        checksum.write_bytes(manifest(directory))


def upload(cfg, version):
    local_credentials()
    directory = source_directory(cfg, version)
    prepare(directory)
    s3 = client()
    bucket = cfg['artifacts']['bucket']
    existing = {o['Key'] for page in s3.get_paginator('list_objects_v2').paginate(
        Bucket=bucket, Prefix=version + '/') for o in page.get('Contents', [])}
    records = []
    # Publish checksum last, after every model/tokenizer/metadata object is verified.
    paths = sorted(p for p in directory.iterdir() if p.is_file() and p.name != 'model.sha256')
    paths.append(directory / 'model.sha256')
    for path in paths:
        key = f'{version}/{path.name}'
        data = path.read_bytes()
        if key in existing and get(s3, key, bucket) != data:
            raise ValueError(f'Refusing to overwrite different existing artifact {key}')
        checksum = put_verified(s3, key, data, bucket)
        records.append({'key': key, 'sha256': checksum, 'bytes': len(data)})
        print(json.dumps({'event': 'uploaded_and_verified', **records[-1]}), flush=True)
    public = ROOT / cfg['artifacts']['public_manifest_root'] / version
    public.mkdir(parents=True, exist_ok=True)
    (public / 'model.sha256').write_bytes((directory / 'model.sha256').read_bytes())
    (public / 'version.json').write_bytes((directory / 'version.json').read_bytes())
    report = {'uri': f's3://{bucket}/{version}/', 'all_files_readback_verified': True,
              'files': records, 'manifest_sha256': digest((directory / 'model.sha256').read_bytes())}
    write_json(ROOT / cfg['artifacts']['results_root'] / version / 's3-upload.json', report)


def download_version(cfg, version, destination):
    """Verify a downloaded manifest and every file before future service loading."""
    local_credentials()
    s3 = client()
    bucket = cfg['artifacts']['bucket']
    data = get(s3, f'{version}/model.sha256', bucket)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for line in data.decode().splitlines():
        expected, name = line.split('  ', 1)
        if Path(name).name != name:
            raise ValueError('Unsafe artifact path')
        raw = get(s3, f'{version}/{name}', bucket)
        if digest(raw) != expected:
            raise ValueError(f'Checksum mismatch downloading {name}')
        (destination / name).write_bytes(raw)
    (destination / 'model.sha256').write_bytes(data)
    verify_directory(destination)
    return destination


def package(cfg, version):
    directory = source_directory(cfg, version)
    prepare(directory)
    folder = ROOT / cfg['artifacts']['package_root']
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'pythia-70m-{version}.tar.gz'
    with target.open('wb') as output:
        with gzip.GzipFile(filename='', fileobj=output, mode='wb', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as archive:
                for path in sorted(directory.iterdir()):
                    if path.is_file():
                        raw = path.read_bytes()
                        info = tarfile.TarInfo(path.name)
                        info.size = len(raw)
                        info.mode = 0o644
                        info.mtime = 0
                        archive.addfile(info, io.BytesIO(raw))
    checksum = digest(target.read_bytes())
    (target.with_name(target.name + '.sha256')).write_text(f'{checksum}  {target.name}\n')
    # Independently hash archived members against the same S3 model manifest.
    with tarfile.open(target) as archive:
        for line in (directory / 'model.sha256').read_text().splitlines():
            expected, name = line.split('  ', 1)
            if digest(archive.extractfile(name).read()) != expected:
                raise ValueError('Release member differs from the S3 checksum manifest')
    public = ROOT / cfg['artifacts']['public_manifest_root'] / version
    public.mkdir(parents=True, exist_ok=True)
    (public / 'release.sha256').write_text(f'{checksum}  {target.name}\n')
    write_json(ROOT / cfg['artifacts']['results_root'] / version / 'release-package.json',
               {'path': str(target.relative_to(ROOT)), 'archive_sha256': checksum,
                'model_manifest_sha256': digest((directory / 'model.sha256').read_bytes()),
                'archive_members_verified': True, 'published': False})
    print(f'Packaged and verified {target}; not published', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['upload', 'package', 'download'])
    ap.add_argument('--version', default='v1')
    ap.add_argument('--destination')
    args = ap.parse_args()
    cfg = read_config()
    if args.action == 'upload':
        upload(cfg, args.version)
    elif args.action == 'package':
        package(cfg, args.version)
    else:
        if not args.destination:
            ap.error('--destination is required')
        download_version(cfg, args.version, args.destination)
