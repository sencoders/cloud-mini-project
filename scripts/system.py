"""Idempotent whole-system bootstrap; never relabel or retrain existing data."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ['KUBECONFIG'] = str(ROOT / '.local/kubeconfig')


def run(args, capture=False):
    return subprocess.run(args, cwd=ROOT, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def down_command():
    name = os.environ.get('CLUSTER_NAME', 'command-parser')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', name):
        raise ValueError('CLUSTER_NAME must name one explicit cluster')
    return ['k3d', 'cluster', 'delete', name]


def up():
    clusters = json.loads(run(['k3d', 'cluster', 'list', '-o', 'json'], capture=True))
    existing = any(c['name'] == 'command-parser' for c in clusters)
    if existing:
        # A repeat invocation must not restart storage, reset replica counts, or
        # overwrite Task 1 evidence. Missing resources fail with actionable errors.
        run(['kubectl', '-n', 'data', 'rollout', 'status', 'deployment/seaweedfs', '--timeout=180s'])
        run(['kubectl', '-n', 'app', 'rollout', 'status', 'deployment/command-parser', '--timeout=180s'])
        run(['kubectl', '-n', 'app', 'get', 'deploy,svc,ingress,hpa'])
        print('Existing system ready; storage, models and replica policy preserved.')
        return
    # Verify/download actual Release files BEFORE creating any cluster. No cached
    # checkpoint fallback on a fresh clone; a missing Release is an explicit blocker.
    repository = os.environ.get('MODEL_RELEASE_REPOSITORY')
    tag = os.environ.get('MODEL_RELEASE_TAG')
    if not repository or not tag:
        raise RuntimeError('Fresh bootstrap requires MODEL_RELEASE_REPOSITORY and MODEL_RELEASE_TAG; publish verified assets first')
    from ci.release import extract_verified
    releases = ROOT / '.local/bootstrap-releases'
    releases.mkdir(parents=True, exist_ok=True)
    for version in ('v1', 'v2'):
        run(['gh', 'release', 'download', tag, '--repo', repository, '--dir', str(releases),
             '--pattern', f'pythia-70m-{version}.tar.gz*', '--clobber'])
        extract_verified(releases / f'pythia-70m-{version}.tar.gz', version,
                         ROOT / '.local/models' / version)
    run(['k3d', 'cluster', 'create', '--config', 'cluster/k3d.yaml'])
    run([sys.executable, 'scripts/task1.py', 'setup'])
    run([sys.executable, 'scripts/task1.py', 'build'])
    # Upload the verified released models into the new local S3, never retrain.
    from training.common import local_credentials
    from worker.storage import client, put_verified
    local_credentials()
    s3 = client()
    for version in ('v1', 'v2'):
        directory = ROOT / '.local/models' / version
        files = sorted(p for p in directory.iterdir() if p.name != 'model.sha256')
        files.append(directory / 'model.sha256')
        for path in files:
            put_verified(s3, f'{version}/{path.name}', path.read_bytes(), 'models')
    run(['docker', 'build', '-t', 'command-parser:task3', '-f', 'service/Dockerfile', '.'])
    run([sys.executable, 'scripts/task4.py', 'deploy'])
    run(['kubectl', 'apply', '-f', 'cluster/hpa.yaml'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['up', 'down'])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.action == 'down':
        if args.dry_run:
            print(' '.join(down_command()))
        else:
            run(down_command())
    elif args.dry_run:
        parser.error('--dry-run is supported for destructive down only')
    else:
        up()
