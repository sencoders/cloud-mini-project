"""Release integrity and non-destructive bootstrap behavior."""
import hashlib
import io
import json
import tarfile

import pytest

from ci import release
from scripts import system


def archive_fixture(tmp_path, monkeypatch, unsafe=False):
    root = tmp_path / 'repo'
    trusted = root / 'models/v1'
    trusted.mkdir(parents=True)
    files = {'version.json': json.dumps({'version': 'v1', 'status': 'complete', 'smoke': False}).encode(),
             'model.safetensors': b'test-only synthetic bytes, never a model'}
    if unsafe:
        files['../escape'] = b'reject'
    manifest = ''.join(f'{hashlib.sha256(raw).hexdigest()}  {name}\n' for name, raw in files.items()).encode()
    files['model.sha256'] = manifest
    (trusted / 'model.sha256').write_bytes(manifest)
    archive = tmp_path / 'model.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        for name, raw in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            stream.addfile(member, io.BytesIO(raw))
    checksum = release.sha256(archive)
    (trusted / 'release.sha256').write_text(checksum)
    archive.with_name(archive.name + '.sha256').write_text(checksum)
    monkeypatch.setattr(release, 'ROOT', root)
    return archive


def test_release_verifies_every_member(tmp_path, monkeypatch):
    archive = archive_fixture(tmp_path, monkeypatch)
    assert release.extract_verified(archive, 'v1', tmp_path / 'out')['verified_members'] == 3


def test_release_rejects_tampering(tmp_path, monkeypatch):
    archive = archive_fixture(tmp_path, monkeypatch)
    archive.write_bytes(archive.read_bytes() + b'tampered')
    with pytest.raises(ValueError, match='checksum'):
        release.extract_verified(archive, 'v1', tmp_path / 'out')


def test_release_rejects_path_traversal(tmp_path, monkeypatch):
    archive = archive_fixture(tmp_path, monkeypatch, unsafe=True)
    with pytest.raises(ValueError, match='Unsafe'):
        release.extract_verified(archive, 'v1', tmp_path / 'out')
    assert not (tmp_path / 'escape').exists()


def test_existing_cluster_up_does_not_mutate_storage(monkeypatch):
    calls = []
    def run(args, capture=False):
        calls.append(args)
        return '[{"name":"command-parser"}]' if capture else ''
    monkeypatch.setattr(system, 'run', run)
    system.up()
    assert all('delete' not in c and 'apply' not in c and 'create' not in c for c in calls)
    assert any('deployment/seaweedfs' in c for c in calls)


def test_down_deletes_only_named_cluster():
    assert system.down_command() == ['k3d', 'cluster', 'delete', 'command-parser']


def test_fresh_bootstrap_requires_release_before_mutation(monkeypatch):
    monkeypatch.setattr(system, 'run', lambda *a, **kw: '[]')
    monkeypatch.delenv('MODEL_RELEASE_REPOSITORY', raising=False)
    monkeypatch.delenv('MODEL_RELEASE_TAG', raising=False)
    with pytest.raises(RuntimeError, match='publish verified assets first'):
        system.up()
