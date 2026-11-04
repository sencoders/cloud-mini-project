#!/usr/bin/env python3
"""Logged local orchestration. Invoke with .venv312/bin/python scripts/task1.py ACTION."""
import argparse
import datetime
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
from worker.label import encode, load_pool
from worker.storage import client, get, keys, put_verified, sha256  # noqa: E402

LOCAL = ROOT / '.local'
LOCAL.mkdir(exist_ok=True, mode=0o700)
LOCAL.chmod(0o700)
os.environ['KUBECONFIG'] = str(LOCAL / 'kubeconfig')
LOG = ROOT / 'results' / 'commands.log'


def command(argv, stdin=None, capture=False, sensitive=False):
    with LOG.open('a') as log:
        log.write(f'\n{datetime.datetime.now(datetime.timezone.utc).isoformat()} $ {" ".join(argv)}\n')
        log.flush()
        p = subprocess.run(argv, input=stdin, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
        log.write('[private configuration output omitted]\n' if sensitive else p.stdout)
    if not capture:
        print(p.stdout, end='', flush=True)
    if p.returncode:
        raise RuntimeError(f'Command failed ({p.returncode}): {argv}')
    return p.stdout


def kube(*args, **kwargs):
    return command(['kubectl', *args], **kwargs)


def credentials():
    path = LOCAL / 'credentials.json'
    if not path.exists():
        path.write_text(json.dumps({'AWS_ACCESS_KEY_ID': secrets.token_hex(12),
                                    'AWS_SECRET_ACCESS_KEY': secrets.token_hex(24)}))
        path.chmod(0o600)
    env = json.loads(path.read_text())
    os.environ.update(env)
    os.environ['S3_ENDPOINT'] = 'http://127.0.0.1:8333'
    return env


def setup():
    config = command(['k3d', 'kubeconfig', 'get', 'command-parser'], capture=True, sensitive=True)
    (LOCAL / 'kubeconfig').write_text(config)
    (LOCAL / 'kubeconfig').chmod(0o600)
    kube('apply', '-f', 'cluster/storage.yaml')
    env = credentials()
    auth = {'identities': [{'name': 'task1', 'credentials': [{
        'accessKey': env['AWS_ACCESS_KEY_ID'], 'secretKey': env['AWS_SECRET_ACCESS_KEY']}],
        'actions': ['Admin', 'Read', 'Write', 'List', 'Tagging']} ]}
    for ns, name, values in (
            ('data', 'seaweedfs-auth', {'s3.json': json.dumps(auth)}),
            ('pipeline', 's3-client', env)):
        secret = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': name, 'namespace': ns},
                  'type': 'Opaque', 'stringData': values}
        kube('apply', '-f', '-', stdin=json.dumps(secret))
    kube('-n', 'data', 'rollout', 'status', 'deployment/seaweedfs', '--timeout=180s')
    s3 = client()
    existing = {b['Name'] for b in s3.list_buckets()['Buckets']}
    for bucket in ('datasets', 'models'):
        if bucket not in existing:
            s3.create_bucket(Bucket=bucket)
    raw = (ROOT / 'data/commands_pool.jsonl').read_bytes()
    digest = put_verified(s3, 'commands_pool.jsonl', raw)
    put_verified(s3, '_storage-test/roundtrip', b'Task 1 S3 round trip\n')
    s3.delete_object(Bucket='datasets', Key='_storage-test/roundtrip')
    report = {'buckets': [b['Name'] for b in s3.list_buckets()['Buckets']],
              'pool_bytes': len(raw), 'pool_sha256': digest,
              'download_matches_original': get(s3, 'commands_pool.jsonl') == raw,
              'roundtrip_put_get_delete': True}
    (ROOT / 'results/storage.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


def launch(smoke):
    credentials()
    if not smoke:
        gate = json.loads((ROOT / 'results/smoke/counts.json').read_text())
        storage = json.loads((ROOT / 'results/storage.json').read_text())
        concurrency = json.loads((ROOT / 'results/smoke/concurrency.json').read_text())
        if gate['input'] != 5 or not gate['all_ids_accounted_for'] or gate['kept'] != 5:
            raise RuntimeError('Five-command smoke gate failed')
        s3 = client()
        sample = load_pool(get(s3, 'commands_pool.jsonl'))[:5]
        for index in range(2):
            manifest = json.loads(get(s3, f'teacher/smoke-json/progress/shard-{index}/manifest.json'))
            if (manifest['prompt_sha256'] != sha256((ROOT / 'prompts/teacher_prompt.txt').read_bytes())
                    or manifest['pool_sha256'] != sha256(b''.join(encode(r) for r in sample))
                    or manifest.get('format') != 'json'):
                raise RuntimeError('Smoke run configuration is stale')
        if not storage['download_matches_original'] or not concurrency['overlap_seconds'] > 0:
            raise RuntimeError('Storage/concurrency gate failed')
    run = 'smoke-json' if smoke else 'teacher'
    prefix = 'teacher/smoke-json' if smoke else 'teacher'
    template = (ROOT / 'cluster/jobs.yaml').read_text()
    for index in range(2):
        manifest = template.replace('teacher-SHARD', f'{run}-{index}').replace(
            'run: teacher', f'run: {run}').replace("value: 'SHARD'", f"value: '{index}'").replace(
            'value: teacher}', f'value: {prefix}}}').replace(
            "name: LIMIT, value: '0'", f"name: LIMIT, value: '{5 if smoke else 0}'")
        path = ROOT / 'results' / f'{run}-job-{index}.yaml'
        path.write_text(manifest)
        kube('apply', '-f', str(path))


def snapshot(run):
    credentials()
    folder = ROOT / 'results' / ('smoke' if run == 'smoke' else 'full')
    folder.mkdir(exist_ok=True)
    pods = json.loads(kube('-n', 'pipeline', 'get', 'pods', '-l', f'run={"smoke-json" if run == "smoke" else run}', '-o', 'json', capture=True))
    (folder / 'pods.json').write_text(json.dumps(pods, indent=2))
    job_json = kube('-n', 'pipeline', 'get', 'jobs', '-l',
                    f'run={"smoke-json" if run == "smoke" else run}', '-o', 'json', capture=True)
    (folder / 'jobs.json').write_text(job_json)
    intervals = {}
    for pod in pods['items']:
        name = pod['metadata']['name']
        if pod.get('status', {}).get('containerStatuses') and any(
                'running' in c['state'] or 'terminated' in c['state']
                for c in pod['status']['containerStatuses']):
            logs = kube('-n', 'pipeline', 'logs', name, '--timestamps', capture=True)
            (folder / f'{name}.log').write_text(logs)
        for status in pod.get('status', {}).get('containerStatuses', []):
            state = status['state']
            if 'terminated' in state:
                interval = state['terminated']
                start, end = interval['startedAt'], interval['finishedAt']
            elif 'running' in state:
                start = state['running']['startedAt']
                end = datetime.datetime.now(datetime.timezone.utc).isoformat()
            else:
                continue
            intervals[name] = [start, end]
    starts = [datetime.datetime.fromisoformat(v[0].replace('Z', '+00:00')) for v in intervals.values()]
    ends = [datetime.datetime.fromisoformat(v[1].replace('Z', '+00:00')) for v in intervals.values()]
    overlap = max(0, (min(ends) - max(starts)).total_seconds()) if len(starts) == 2 else 0
    (folder / 'concurrency.json').write_text(json.dumps(
        {'intervals': intervals, 'overlap_seconds': overlap}, indent=2) + '\n')
    s3 = client()
    prefix = 'teacher/smoke-json' if run == 'smoke' else 'teacher'
    checkpoints = [k for k in keys(s3, prefix + '/progress/') if k.endswith('.json') and not k.endswith('manifest.json')]
    report = {'run': run, 'durable_completed': len(checkpoints), 'expected': 5 if run == 'smoke' else 3000,
              'overlap_seconds': overlap, 'objects': keys(s3, prefix + '/')}
    (folder / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'objects'}, indent=2))
    kube('-n', 'pipeline', 'get', 'jobs,pods', '-o', 'wide')



def finish():
    """Observe existing Jobs and finalize; never launches or repeats inference."""
    deadline = time.monotonic() + 20 * 3600
    while time.monotonic() < deadline:
        jobs = json.loads(kube('-n', 'pipeline', 'get', 'jobs', '-l', 'run=teacher',
                               '-o', 'json', capture=True))['items']
        if len(jobs) != 2:
            raise RuntimeError('Expected exactly two full-run Jobs')
        snapshot('teacher')
        if any(any(c['type'] == 'Failed' and c['status'] == 'True'
                   for c in j.get('status', {}).get('conditions', [])) for j in jobs):
            raise RuntimeError('A teacher Job failed; inspect saved logs and resume it')
        if all(j.get('status', {}).get('succeeded', 0) == 1 for j in jobs):
            credentials()
            argv = [sys.executable, '-m', 'worker.clean']
            command(argv)
            checksum = (ROOT / 'results/full/train.sha256').read_text()
            command(argv)
            repeated = (ROOT / 'results/full/train.sha256').read_text()
            if checksum != repeated:
                raise RuntimeError('Repeated cleaning produced different bytes')
            verification = {'first_checksum': checksum.strip(),
                            'second_checksum': repeated.strip(), 'match': True}
            (ROOT / 'results/full/reproducibility.json').write_text(
                json.dumps(verification, indent=2) + '\n')
            counts = json.loads((ROOT / 'results/full/counts.json').read_text())
            report = ['# Task 1 measured results', '',
                      'All 3,000 source IDs are accounted for exactly once across two shards.', '',
                      '| Category | Count |', '|---|---:|']
            report += [f'| {k} | {counts[k]} |' for k in (
                'input', 'a_invalid_json', 'b_wrong_keys', 'c_invalid_intent',
                'd_invalid_slot', 'duplicates', 'kept')]
            report += ['', 'SHA-256: `' + counts['sha256'] + '`.', '',
                       'Two independent cleaning runs produced the same checksum.',
                       'See results/full/ for raw shards, logs, ID accounting and concurrency evidence.',
                       'No Task 2 training was started.']
            (ROOT / 'report/task1-results.md').write_text('\n'.join(report) + '\n')
            print('FULL TASK 1 LABELLING AND CLEANING COMPLETE', flush=True)
            return
        time.sleep(30)
    raise TimeoutError('20-hour monitoring limit reached; Jobs were left intact')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['setup', 'build', 'smoke', 'launch', 'status', 'clean', 'finish', 'down'])
    ap.add_argument('--run', choices=['smoke', 'teacher'], default='teacher')
    args = ap.parse_args()
    if args.action == 'setup':
        setup()
    elif args.action == 'build':
        command(['docker', 'build', '-t', 'command-teacher:task1', '-f', 'worker/Dockerfile', '.'])
        command(['k3d', 'image', 'import', 'command-teacher:task1', '-c', 'command-parser'])
    elif args.action in ('smoke', 'launch'):
        launch(args.action == 'smoke')
    elif args.action == 'status':
        snapshot(args.run)
    elif args.action == 'clean':
        credentials()
        smoke = args.run == 'smoke'
        command([sys.executable, '-m', 'worker.clean', '--prefix', 'teacher/smoke-json' if smoke else 'teacher',
                 '--limit', '5' if smoke else '0', '--output', 'smoke/v1' if smoke else 'v1',
                 '--results', 'results/smoke' if smoke else 'results/full'])
    elif args.action == 'finish':
        finish()
    elif args.action == 'down':
        command(['k3d', 'cluster', 'delete', 'command-parser'])


if __name__ == '__main__':
    main()
