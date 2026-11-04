#!/usr/bin/env python3
"""Real Task 3 Docker test, fixed at 1 CPU / 1 GiB, no mounted model weights."""
import base64
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ['KUBECONFIG'] = str(ROOT / '.local/kubeconfig')
ARTIFACT_ROOT = ROOT / 'results/task3'
OUT = ARTIFACT_ROOT / 'docker-runs' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
OUT.mkdir(parents=True, exist_ok=True)
COMMANDS = OUT / 'docker-test-commands.log'


def run(argv, private=False, check=True):
    process = subprocess.run(argv, text=True, capture_output=True)
    with COMMANDS.open('a') as file:
        file.write('$ ' + ' '.join(argv) + '\n')
        file.write('[private runtime configuration omitted]\n' if private else process.stdout)
        file.write(process.stderr)
    if check and process.returncode:
        raise RuntimeError(f'Command failed: {argv[0:3]} (see {COMMANDS})')
    return process.stdout


def write(name, value):
    if name == 'docker-results.json':
        value['evidence_directory'] = str(OUT.relative_to(ROOT))
        (ARTIFACT_ROOT / name).write_text(json.dumps(value, indent=2) + '\n')
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')


def http(path, body=None):
    request = urllib.request.Request('http://127.0.0.1:18000' + path,
               data=None if body is None else json.dumps(body).encode(),
               headers={'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, dict(response.headers), response.read().decode()


def wait_ready(name, label):
    observations = []
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            health = http('/healthz')[0]
            status, _, body = http('/readyz')
            observations.append({'time': time.time(), 'health': health, 'ready': status})
            if status == 200:
                write(f'{label}-readiness.json', observations)
                return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    write(f'{label}-readiness.json', observations)
    raise RuntimeError('Container did not become ready at the required limits')


def inspect(name):
    info = json.loads(run(['docker', 'inspect', name], private=True))[0]
    return {'state': info['State'], 'limits': {k: info['HostConfig'][k]
            for k in ('NanoCpus', 'Memory', 'MemorySwap')}, 'image_id': info['Image']}


def main():
    image = json.loads(run(['docker', 'image', 'inspect', 'command-parser:task3']))[0]
    write('image.json', image)
    size_cli = json.loads(run(['docker', 'image', 'ls', 'command-parser:task3', '--format', '{{json .}}']))
    displayed = size_cli['Size']
    multipliers = {'GB': 10**9, 'MB': 10**6, 'kB': 10**3, 'B': 1}
    unit = next(u for u in multipliers if displayed.endswith(u))
    disk_bytes = float(displayed[:-len(unit)]) * multipliers[unit]
    if max(image['Size'], disk_bytes) > 2_000_000_000:
        raise RuntimeError('Image exceeds 2 GB; refusing to claim compliance')
    audit = run(['docker', 'run', '--rm', '--entrypoint', 'python', 'command-parser:task3', '-c',
                 "import json,pathlib,torch; p=pathlib.Path('/app'); files=[str(x) for x in p.rglob('*') if x.suffix in ('.safetensors','.bin','.pt','.pth')]; assert not files; assert torch.version.cuda is None; print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,'embedded_weight_files':files}))"])
    (OUT / 'image-audit.json').write_text(audit)
    secret = json.loads(run(['kubectl', '-n', 'pipeline', 'get', 'secret', 's3-client', '-o', 'json'], private=True))
    environment = {key: base64.b64decode(secret['data'][key]).decode()
                   for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY')}
    private = ROOT / '.local/task3-secret.env'
    private.write_text(''.join(f'{k}={v}\n' for k, v in environment.items()))
    private.chmod(0o600)
    rows = [json.loads(line) for line in (ROOT / 'data/validation.jsonl').read_text().splitlines()][:50]
    schema = json.loads((ROOT / 'data/schema.json').read_text())['json_schema']
    from jsonschema import Draft202012Validator
    validate = Draft202012Validator(schema)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')
    report = {'image_content_bytes': image['Size'], 'image_disk_size_display': displayed, 'credentials_source': 'Kubernetes Secret pipeline/s3-client'}
    for label, fault in (('limited', '0'), ('fault', '1')):
        name = f'parser-task3-{label}-{stamp}'
        stopped = threading.Event()
        sampler = None
        try:
            run(['docker', 'run', '-d', '--name', name, '--hostname', name,
                 '--network', 'k3d-command-parser', '--cpus=1', '--memory=1g', '--memory-swap=1g',
                 '-p', '127.0.0.1:18000:8000', '--env-file', str(private),
                 '-e', 'MODEL_URI=s3://models/v1/', '-e', 'MODEL_VERSION=v1',
                 '-e', 'S3_ENDPOINT=http://k3d-command-parser-server-0:30333',
                 '-e', 'MAX_NEW_TOKENS=128', '-e', f'FAULT_INJECT={fault}', 'command-parser:task3'])

            def sample():
                with (OUT / f'{label}-memory-samples.jsonl').open('w') as file:
                    while not stopped.is_set():
                        value = subprocess.run(['docker', 'stats', '--no-stream', '--format', '{{json .}}', name],
                                               capture_output=True, text=True)
                        if value.stdout.strip():
                            file.write(json.dumps({'time': time.time(), 'stats': json.loads(value.stdout)}) + '\n')
                            file.flush()
                        stopped.wait(0.2)
            sampler = threading.Thread(target=sample, daemon=True)
            sampler.start()
            wait_ready(name, label)
            records = []
            for row in rows if fault == '0' else rows[:1]:
                tick = time.perf_counter()
                status, headers, raw = http('/parse', {'text': row['text']})
                item = {'id': row['id'], 'status': status, 'headers': headers,
                        'body': raw, 'seconds': time.perf_counter() - tick}
                records.append(item)
                with (OUT / f'{label}-responses.jsonl').open('a') as file:
                    file.write(json.dumps(item) + '\n')
                if fault == '0':
                    if status == 200:
                        validate.validate(json.loads(raw))
                elif status != 500 or json.loads(raw) != {'error': 'invalid_model_output'}:
                    raise RuntimeError('Fault injection did not produce exact required response')
            peak = run(['docker', 'exec', name, 'cat', '/sys/fs/cgroup/memory.peak']).strip()
            events = run(['docker', 'exec', name, 'cat', '/sys/fs/cgroup/memory.events'])
            report[label] = {'requests': len(records), 'successful_http_200': sum(r['status'] == 200 for r in records),
                             'statuses': [r['status'] for r in records], 'cgroup_peak_bytes': int(peak),
                             'cgroup_memory_events': events, 'inspection': inspect(name),
                             'health_status': http('/healthz')[0], 'ready_status': http('/readyz')[0]}
            assert report[label]['inspection']['limits']['NanoCpus'] == 1_000_000_000
            assert report[label]['inspection']['limits']['Memory'] == 1024 ** 3
            assert not report[label]['inspection']['state']['OOMKilled']
        except BaseException as error:
            report[label] = {'failure_type': type(error).__name__, 'failure': str(error), 'inspection': inspect(name)}
            raise
        finally:
            stopped.set()
            if sampler:
                sampler.join(timeout=5)
            (OUT / f'{label}-container.log').write_text(run(['docker', 'logs', name], check=False))
            run(['docker', 'stop', '--time', '30', name], check=False)
            report.setdefault(label, {})['final_inspection'] = inspect(name)
            write('docker-results.json', report)
    from student.runtime import extract_json
    expected = {r['id']: r['prediction'] for r in map(json.loads,
        (ROOT / 'results/task2/evaluation/student_v1_raw_predictions.jsonl').read_text().splitlines())}
    actual = [json.loads(line) for line in (OUT / 'limited-responses.jsonl').read_text().splitlines()]
    matches = sum(r['status'] == 200 and json.loads(r['body']) == extract_json(expected[r['id']])[1] for r in actual)
    report['task2_prediction_comparison'] = {'compared': len(actual), 'identical_frames': matches}
    write('docker-results.json', report)
    if report['limited']['successful_http_200'] != 50:
        raise RuntimeError('Some sequential requests failed; see genuine results')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
