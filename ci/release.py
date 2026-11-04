"""Verify Release archives against committed checksums before safe extraction."""
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def extract_verified(archive, version, destination):
    archive, destination = Path(archive), Path(destination)
    trusted = ROOT / 'models' / version
    expected = (trusted / 'release.sha256').read_text().split()[0]
    sidecar = archive.with_name(archive.name + '.sha256')
    if sha256(archive) != expected or sidecar.read_text().split()[0] != expected:
        raise ValueError('Release archive checksum differs from committed checksum')
    manifest = (trusted / 'model.sha256').read_bytes()
    hashes = dict(line.split('  ', 1)[::-1] for line in manifest.decode().splitlines())
    with tarfile.open(archive) as package:
        members = package.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)) or set(names) != set(hashes) | {'model.sha256'}:
            raise ValueError('Unexpected, duplicate or missing archive member')
        if sum(m.size for m in members) > 2_000_000_000:
            raise ValueError('Oversized archive')
        destination.mkdir(parents=True, exist_ok=True)
        for member in members:
            if not member.isfile() or Path(member.name).name != member.name:
                raise ValueError('Unsafe archive member')
            raw = package.extractfile(member).read()
            if member.name == 'model.sha256':
                if raw != manifest:
                    raise ValueError('Untrusted model manifest')
            elif hashlib.sha256(raw).hexdigest() != hashes[member.name]:
                raise ValueError('Model file checksum mismatch')
            (destination / member.name).write_bytes(raw)
    info = json.loads((destination / 'version.json').read_text())
    if info['version'] != version or info['status'] != 'complete' or info['smoke']:
        raise ValueError('Incomplete or incorrect model version')
    return {'version': version, 'archive_sha256': expected, 'verified_members': len(names),
            'published': False}
