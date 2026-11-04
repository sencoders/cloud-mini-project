import json
from pathlib import Path

import yaml


def test_empty_endpoint_slice_has_zero_ready_backends(monkeypatch):
    from scripts import task4
    monkeypatch.setattr(task4, 'kube', lambda *a, **k: json.dumps({'items': [{'endpoints': None}]}))
    assert task4.endpoints()[0] == 0


def test_loading_and_terminating_endpoints_do_not_receive_traffic(monkeypatch):
    from scripts import task4
    response = {'items': [{'endpoints': [
        {'conditions': {'ready': False, 'terminating': False}},
        {'conditions': {'ready': False, 'terminating': True}},
        {'conditions': {'ready': True}}]}]}
    monkeypatch.setattr(task4, 'kube', lambda *a, **k: json.dumps(response))
    assert task4.endpoints()[0] == 1


def test_manifest_has_real_readiness_and_secret_credentials():
    docs = list(yaml.safe_load_all(Path('cluster/app.yaml').read_text()))
    deployment = next(d for d in docs if d['kind'] == 'Deployment')
    container = deployment['spec']['template']['spec']['containers'][0]
    assert deployment['spec']['replicas'] == 2
    assert deployment['spec']['strategy']['rollingUpdate']['maxUnavailable'] == 0
    assert container['readinessProbe']['httpGet']['path'] == '/readyz'
    assert container['livenessProbe']['httpGet']['path'] == '/healthz'
    assert container['envFrom'] == [{'secretRef': {'name': 'parser-s3'}}]
    assert not any(v['name'].startswith('AWS_') for v in container['env'])
    hpa = yaml.safe_load(Path('cluster/hpa.yaml').read_text())
    assert hpa['spec']['minReplicas'] == 1 and hpa['spec']['maxReplicas'] == 2
    assert hpa['spec']['metrics'][0]['resource']['target']['averageUtilization'] == 70


def test_version_verification_waits_for_ingress_and_retains_model_500s(monkeypatch, tmp_path):
    from scripts import task4
    monkeypatch.setattr(task4, 'ROOT', tmp_path)
    monkeypatch.setattr(task4, 'OUT', tmp_path / 'results/task4')
    monkeypatch.setattr(task4, 'ingress_ready', lambda: 200)
    monkeypatch.setattr(task4.time, 'sleep', lambda _: None)
    values = iter([{'status': 200, 'headers': {'X-Model-Version': 'v1'}, 'body': '{}'}] +
                  [{'status': 500, 'headers': {'X-Model-Version': 'v2'},
                    'body': '{"error":"invalid_model_output"}'}] * 3)
    monkeypatch.setattr(task4, 'probe', lambda: next(values))
    result = task4.verify_version('v2')
    assert result['probe_count'] == 4
    assert result['model_rejection_count'] == 3
    assert result['response']['status'] == 500  # Never called a successful inference.
    trace = json.loads((tmp_path / result['trace']).read_text())
    assert trace[0]['version_matches'] is False
    assert [r['response']['status'] for r in trace] == [200, 500, 500, 500]


def test_unexpected_500_does_not_pass_rollout_verification(monkeypatch, tmp_path):
    import pytest
    from scripts import task4
    monkeypatch.setattr(task4, 'ROOT', tmp_path)
    monkeypatch.setattr(task4, 'OUT', tmp_path / 'results/task4')
    monkeypatch.setattr(task4, 'ingress_ready', lambda: 200)
    monkeypatch.setattr(task4.time, 'sleep', lambda _: None)
    ticks = iter(range(20))
    monkeypatch.setattr(task4.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(task4, 'probe', lambda: {'status': 500,
        'headers': {'X-Model-Version': 'v2'}, 'body': '{"error":"unexpected_failure"}'})
    with pytest.raises(TimeoutError):
        task4.verify_version('v2', timeout=5)
    trace_file = next((tmp_path / 'results/task4/version-verification').glob('*.json'))
    assert all(not row['version_matches'] for row in json.loads(trace_file.read_text()))


def test_completed_load_evidence_is_not_overwritten(monkeypatch, tmp_path):
    import pytest
    from scripts import task4
    monkeypatch.setattr(task4, 'OUT', tmp_path)
    folder = tmp_path / 'load-balancing'
    folder.mkdir()
    (folder / 'execution.json').write_text('{"original":true}')
    with pytest.raises(FileExistsError, match='Preserving completed evidence'):
        task4.run_load('load-balancing')
    assert (folder / 'execution.json').read_text() == '{"original":true}'


def test_failed_http_requests_do_not_cause_completed_load_to_repeat(monkeypatch, tmp_path):
    from scripts import task4
    monkeypatch.setattr(task4, 'OUT', tmp_path)
    path = tmp_path / 'rolling'
    path.mkdir()
    record = {'returncode': 1, 'orchestration_error': None,
              'actions': [{'action': 'update-v2'}, {'action': 'rollback-v1'}]}
    (path / 'execution.json').write_text(json.dumps(record))
    assert task4.load_finished('rolling')  # Completed experiment, unmet HTTP SLO.
    record['orchestration_error'] = 'API timeout'
    (path / 'execution.json').write_text(json.dumps(record))
    assert not task4.load_finished('rolling')


def test_successful_cold_starts_are_not_repeated(monkeypatch, tmp_path):
    import pytest
    from scripts import task4
    monkeypatch.setattr(task4, 'OUT', tmp_path)
    (tmp_path / 'cold-starts').mkdir()
    with pytest.raises(FileExistsError, match='Preserving existing cold-start'):
        task4.cold_starts()
