#!/usr/bin/env python3
"""Deploy and measure Task 4 against actual Kubernetes and unchanged Locust code."""
import argparse
import base64
import datetime
import json
import os
from pathlib import Path
import statistics
import signal
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ['KUBECONFIG'] = str(ROOT / '.local/kubeconfig')
OUT = ROOT / 'results/task4'
OUT.mkdir(parents=True, exist_ok=True)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def run(argv, private=False, stdin=None, check=True):
    p = subprocess.run(argv, input=stdin, text=True, capture_output=True)
    with (OUT / 'commands.log').open('a') as file:
        file.write('\n' + datetime.datetime.now(datetime.timezone.utc).isoformat() + ' $ ' + ' '.join(argv) + '\n')
        file.write('[private configuration omitted]\n' if private else p.stdout)
        file.write(p.stderr)
    if check and p.returncode:
        raise RuntimeError(f'Command failed: {argv[:4]} (see results/task4/commands.log)')
    return p.stdout


def kube(*args, **kwargs):
    return run(['kubectl', *args], **kwargs)


def pods():
    return json.loads(kube('-n', 'app', 'get', 'pods', '-l', 'app=command-parser', '-o', 'json'))['items']


def endpoints():
    value = json.loads(kube('-n', 'app', 'get', 'endpointslices', '-l',
                            'kubernetes.io/service-name=command-parser', '-o', 'json'))
    ready = [e for item in value['items'] for e in (item.get('endpoints') or []) if e.get('conditions', {}).get('ready')]
    return len(ready), value


def pod_ready(pod):
    return any(c['type'] == 'Ready' and c['status'] == 'True' for c in pod.get('status', {}).get('conditions', []))


def wait_replicas(count, timeout=180):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        values = pods()
        if len(values) == count and all(pod_ready(p) for p in values) and endpoints()[0] == count:
            return values
        time.sleep(1)
    raise TimeoutError(f'Did not reach exactly {count} Ready replicas')


def logs(folder, values=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for p in values if values is not None else pods():
        name = p['metadata']['name']
        statuses = p.get('status', {}).get('containerStatuses', [])
        if statuses and any('running' in s['state'] or 'terminated' in s['state'] for s in statuses):
            (folder / f'{name}.log').write_text(kube('-n', 'app', 'logs', name, '--timestamps', check=False))


def snapshot(folder):
    folder = Path(folder)
    values = pods()
    write(folder / 'pods.json', values)
    count, slices = endpoints()
    write(folder / 'endpointslices.json', slices)
    (folder / 'resources.json').write_text(kube('-n', 'app', 'get', 'deploy,svc,ingress,hpa', '-o', 'json'))
    (folder / 'top.txt').write_text(kube('-n', 'app', 'top', 'pods', check=False))
    logs(folder, values)
    return count


def probe():
    req = urllib.request.Request('http://localhost:8080/parse',
              data=json.dumps({'text': 'what is the weather in london'}).encode(),
              headers={'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return {'status': response.status, 'headers': dict(response.headers),
                'body': response.read().decode(), 'time': time.time()}


def deploy():
    # Keep the data namespace, node containers, PV and model objects untouched.
    before = json.loads(kube('-n', 'data', 'get', 'pods', '-o', 'json'))
    write(OUT / 'storage-before.json', before)
    run(['k3d', 'image', 'import', 'command-parser:task3', '-c', 'command-parser'])
    lb = json.loads(run(['docker', 'inspect', 'k3d-command-parser-serverlb'], private=True))[0]
    bindings = lb['HostConfig'].get('PortBindings', {})
    if not any(p.get('HostPort') == '8080' for values in bindings.values() for p in values or []):
        run(['k3d', 'node', 'edit', 'k3d-command-parser-serverlb', '--port-add', '127.0.0.1:8080:80'])
    namespace = {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': 'app'}}
    kube('apply', '-f', '-', stdin=json.dumps(namespace))
    original = json.loads(kube('-n', 'pipeline', 'get', 'secret', 's3-client', '-o', 'json', private=True))
    secret = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'parser-s3', 'namespace': 'app'},
              'type': 'Opaque', 'data': {k: original['data'][k] for k in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY')}}
    kube('apply', '-f', '-', stdin=json.dumps(secret))
    kube('apply', '-f', 'cluster/app.yaml')
    observations = []
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        values = pods()
        count, slices = endpoints()
        observations.append({'time': time.time(), 'ready_endpoints': count,
                             'pod_ready': {p['metadata']['name']: pod_ready(p) for p in values}})
        if len(values) == 2 and all(pod_ready(p) for p in values) and count == 2:
            break
        time.sleep(0.5)
    else:
        raise TimeoutError('Initial deployment did not become ready')
    write(OUT / 'initial-readiness.json', observations)
    snapshot(OUT / 'initial')
    result = probe()
    write(OUT / 'ingress-probe.json', result)
    if result['status'] != 200:
        raise RuntimeError('Ingress did not return HTTP 200')
    after = json.loads(kube('-n', 'data', 'get', 'pods', '-o', 'json'))
    assert [p['metadata']['uid'] for p in before['items']] == [p['metadata']['uid'] for p in after['items']]
    write(OUT / 'storage-after-deploy.json', after)
    print(json.dumps({'event': 'deployment_ready', 'replicas': 2, 'probe': result}), flush=True)


def cold_starts():
    if (OUT / 'cold-starts').exists():
        raise FileExistsError('Preserving existing cold-start evidence; use resume')
    measurements = []
    for number in range(1, 4):
        folder = OUT / 'cold-starts' / f'run-{number}'
        old = wait_replicas(2)
        logs(folder / 'before', old)
        old_ids = {p['metadata']['uid'] for p in old}
        kube('-n', 'app', 'delete', 'pod', '-l', 'app=command-parser', '--wait=false')
        trace = []
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            values = pods()
            current = [p for p in values if p['metadata']['uid'] not in old_ids]
            count, slices = endpoints()
            trace.append({'time': time.time(), 'ready_endpoints': count,
                          'pods': {p['metadata']['name']: pod_ready(p) for p in current}})
            if len(values) == len(current) == 2 and all(pod_ready(p) for p in current) and count == 2:
                durations = []
                for p in current:
                    created = datetime.datetime.fromisoformat(p['metadata']['creationTimestamp'].replace('Z', '+00:00'))
                    ready = next(c for c in p['status']['conditions'] if c['type'] == 'Ready')
                    at = datetime.datetime.fromisoformat(ready['lastTransitionTime'].replace('Z', '+00:00'))
                    durations.append({'pod': p['metadata']['name'], 'creation': created.isoformat(),
                                      'ready': at.isoformat(), 'seconds': (at - created).total_seconds()})
                measurement = {'run': number, 'pods': durations,
                               'median_seconds': statistics.median(d['seconds'] for d in durations),
                               'no_ready_endpoints_observed': any(t['ready_endpoints'] == 0 for t in trace)}
                measurements.append(measurement)
                write(folder / 'measurement.json', measurement)
                write(folder / 'readiness-trace.json', trace)
                snapshot(folder / 'ready')
                print(json.dumps({'event': 'cold_start_complete', **measurement}), flush=True)
                break
            time.sleep(0.5)
        else:
            raise TimeoutError('Cold start failed')
    write(OUT / 'cold-starts/summary.json', {'runs': measurements,
          'median_of_run_medians_seconds': statistics.median(r['median_seconds'] for r in measurements),
          'all_six_pod_median_seconds': statistics.median(p['seconds'] for r in measurements for p in r['pods'])})


def ingress_ready():
    try:
        with urllib.request.urlopen('http://localhost:8080/readyz', timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def verify_version(version, timeout=60):
    """Wait for asynchronous Ingress propagation, retaining every failed probe.

    An explicit invalid_model_output 500 proves which version served a request;
    it is recorded as a model failure, never treated as a successful prediction.
    Locust independently counts every such response against the failure rubric.
    """
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = OUT / 'version-verification' / f'{version}-{stamp}.json'
    trace = []
    consecutive = 0
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            readiness = ingress_ready()
            result = probe()
            headers = {k.lower(): v for k, v in result['headers'].items()}
            rejection = result['status'] == 500 and json.loads(result['body']) == {'error': 'invalid_model_output'}
            matches = (readiness == 200 and headers.get('x-model-version') == version
                       and (result['status'] == 200 or rejection))
            trace.append({'ready_status': readiness, 'response': result,
                          'model_output_rejected': rejection, 'version_matches': matches})
        except (OSError, urllib.error.URLError, ValueError) as error:
            matches = False
            trace.append({'time': time.time(), 'error': type(error).__name__, 'detail': str(error)})
        consecutive = consecutive + 1 if matches else 0
        write(path, trace)
        if consecutive >= 3:
            return {'version_verified': version, 'response': result, 'probe_count': len(trace),
                    'model_rejection_count': sum(t.get('model_output_rejected', False) for t in trace),
                    'trace': str(path.relative_to(ROOT))}
        time.sleep(1)
    raise TimeoutError(f'Ingress did not consistently serve {version}; see {path}')


def set_version(version):
    kube('-n', 'app', 'set', 'env', 'deployment/command-parser',
         f'MODEL_URI=s3://models/{version}/', f'MODEL_VERSION={version}')
    kube('-n', 'app', 'rollout', 'status', 'deployment/command-parser', '--timeout=180s')
    wait_replicas(2)
    return verify_version(version)


def rollback():
    kube('-n', 'app', 'rollout', 'undo', 'deployment/command-parser')
    kube('-n', 'app', 'rollout', 'status', 'deployment/command-parser', '--timeout=180s')
    wait_replicas(2)
    return verify_version('v1')


def recover():
    current = wait_replicas(2)
    victim = current[0]
    logs(OUT / 'recovery/before-deletion', current)
    tick = time.perf_counter()
    kube('-n', 'app', 'delete', 'pod', victim['metadata']['name'], '--wait=false')
    restored = wait_replicas(2)
    assert victim['metadata']['uid'] not in {p['metadata']['uid'] for p in restored}
    return {'deleted_pod': victim['metadata']['name'], 'deleted_uid': victim['metadata']['uid'],
            'replicas_restored': len(restored), 'replacement_ready_seconds': time.perf_counter() - tick,
            'replacement_pods': [p['metadata']['name'] for p in restored]}


def run_load(label, duration='2m', events=(), canonical=False):
    folder = OUT / label
    if (folder / 'execution.json').exists():
        raise FileExistsError(f'Preserving completed evidence: {folder}')
    folder.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    prefix = ROOT / 'results/loadtest' if canonical else folder / 'loadtest'
    headers = ROOT / 'results/loadtest_headers.json' if canonical else folder / 'loadtest_headers.json'
    environment['LOADTEST_HEADERS_OUT'] = str(headers)
    argv = [str(ROOT / '.venv-load/bin/locust'), '-f', 'tools/locustfile.py', '--headless',
            '--users', '4', '--spawn-rate', '4', '--run-time', duration,
            '--host', 'http://localhost:8080', '--csv', str(prefix)]
    (folder / 'command.txt').write_text(' '.join(argv) + '\n')
    snapshot(folder / 'before')
    observations, actions = [], []
    failure = None
    with (folder / 'locust.log').open('w') as file:
        p = subprocess.Popen(argv, env=environment, stdout=file, stderr=subprocess.STDOUT)
        started = time.perf_counter()
        pending = list(events)
        try:
            while p.poll() is None:
                elapsed = time.perf_counter() - started
                if pending and elapsed >= pending[0][0]:
                    at, name, callback = pending.pop(0)
                    try:
                        result = callback()
                    except Exception as error:
                        actions.append({'action': name, 'started_at_seconds': elapsed,
                                        'error': type(error).__name__, 'detail': str(error)})
                        write(folder / 'actions.json', actions)
                        raise
                    actions.append({'action': name, 'started_at_seconds': elapsed,
                                    'finished_at_seconds': time.perf_counter() - started, 'result': result})
                    write(folder / 'actions.json', actions)
                    snapshot(folder / name)
                values = pods()
                hpa = json.loads(kube('-n', 'app', 'get', 'hpa', '-o', 'json'))
                observations.append({'time': time.time(), 'elapsed': elapsed,
                    'ready_pods': sum(pod_ready(x) for x in values), 'pods': [x['metadata']['name'] for x in values],
                    'hpa': hpa})
                with (folder / 'top-samples.txt').open('a') as sample:
                    sample.write(str(time.time()) + '\n' + kube('-n', 'app', 'top', 'pods', check=False))
                time.sleep(3)
            if pending:
                raise RuntimeError('Load ended before every scheduled action executed')
        except Exception as error:
            failure = error
        finally:
            if p.poll() is None:
                p.send_signal(signal.SIGINT)
                try:
                    p.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
            write(folder / 'observations.json', observations)
            write(folder / 'execution.json', {'returncode': p.returncode, 'wall_seconds': time.perf_counter() - started,
                  'actions': actions, 'headers_path': str(headers.relative_to(ROOT)),
                  'csv_prefix': str(prefix.relative_to(ROOT)),
                  'orchestration_error': None if failure is None else str(failure)})
    snapshot(folder / 'after')
    if failure is not None:
        raise failure
    print(json.dumps({'event': 'load_complete', 'test': label, 'returncode': p.returncode,
                      'headers': json.loads(headers.read_text())}), flush=True)


def idle_to_one(label):
    history = OUT / 'autoscaling' / f'{label}.json'
    observations = json.loads(history.read_text()) if history.exists() else []
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        values = pods()
        hpa = json.loads(kube('-n', 'app', 'get', 'hpa', 'command-parser', '-o', 'json'))
        observations.append({'time': time.time(), 'ready_pods': sum(pod_ready(p) for p in values), 'hpa': hpa})
        write(OUT / 'autoscaling' / f'{label}.json', observations)
        if len(values) == 1 and pod_ready(values[0]) and hpa['status'].get('desiredReplicas') == 1:
            return
        time.sleep(5)
    raise TimeoutError('HPA did not scale down to one during the measured window')


def experiments():
    if (OUT / 'cold-starts').exists() or (OUT / 'load-balancing/execution.json').exists():
        raise FileExistsError('Preserving existing experiments; use resume')
    wait_replicas(2)
    cold_starts()
    run_load('load-balancing', canonical=True)
    run_load('rolling', events=[(15, 'update-v2', lambda: set_version('v2')), (70, 'rollback-v1', rollback)])
    run_load('recovery', events=[(15, 'delete-pod', recover)])
    kube('apply', '-f', 'cluster/hpa.yaml')
    idle_to_one('initial-idle')
    run_load('autoscaling-load')
    idle_to_one('after-load-idle')
    snapshot(OUT / 'final')
    write(OUT / 'completed.json', {'cold_start_runs': 3, 'load_tests': 4,
          'final_version_probe': probe(), 'all_experiments_executed': True})


def load_finished(label):
    path = OUT / label / 'execution.json'
    if not path.is_file():
        return False
    record = json.loads(path.read_text())
    if record.get('orchestration_error'):
        return False
    required = {'rolling': ['update-v2', 'rollback-v1'], 'recovery': ['delete-pod']}.get(label, [])
    return [a['action'] for a in record.get('actions', [])] == required


def archive_unfinished(label):
    path = OUT / label
    if path.exists():
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        destination = OUT / f'{label}-interrupted-{stamp}'
        path.rename(destination)
        print(json.dumps({'event': 'unfinished_evidence_preserved', 'path': str(destination)}), flush=True)


def resume_remaining():
    """Resume stages without repeating completed experiments or masking failures."""
    if (OUT / 'completed.json').exists():
        print('All experiments already executed; preserving existing evidence.', flush=True)
        return
    if not (OUT / 'cold-starts/summary.json').is_file() or not (OUT / 'load-balancing/execution.json').is_file():
        raise ValueError('Expected completed cold-start and baseline evidence')
    if not load_finished('rolling'):
        archive_unfinished('rolling')
        wait_replicas(2)
        write(OUT / 'resume-restored-v1.json', set_version('v1'))
        run_load('rolling', events=[(15, 'update-v2', lambda: set_version('v2')), (70, 'rollback-v1', rollback)])
    if not load_finished('recovery'):
        archive_unfinished('recovery')
        wait_replicas(2)
        run_load('recovery', events=[(15, 'delete-pod', recover)])
    kube('apply', '-f', 'cluster/hpa.yaml')
    if not load_finished('autoscaling-load'):
        archive_unfinished('autoscaling-load')
        idle_to_one('initial-idle')
        run_load('autoscaling-load')
    idle_to_one('after-load-idle')
    snapshot(OUT / 'final')
    write(OUT / 'completed.json', {'cold_start_runs_preserved': 3,
          'baseline_preserved': True, 'remaining_load_tests_executed': 3,
          'final_version_probe': probe(), 'all_experiments_executed': True})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['deploy', 'experiments', 'resume', 'snapshot'])
    args = parser.parse_args()
    if args.action == 'deploy':
        deploy()
    elif args.action == 'resume':
        resume_remaining()
    elif args.action == 'experiments':
        experiments()
    else:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        folder = OUT / 'status' / stamp
        snapshot(folder)
        print(f'Saved read-only app status to {folder}', flush=True)
