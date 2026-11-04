#!/usr/bin/env python3
"""Summarize genuine Task 4 evidence, including nonzero Locust exits and gaps."""
import csv
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/task4'


def read(path):
    return json.loads(Path(path).read_text())


def load_metrics(folder, prefix=None, headers=None):
    folder = Path(folder)
    prefix = Path(prefix) if prefix else folder / 'loadtest'
    headers = Path(headers) if headers else folder / 'loadtest_headers.json'
    with Path(str(prefix) + '_stats.csv').open() as file:
        aggregate = next(r for r in csv.DictReader(file) if r['Name'] == 'Aggregated')
    text = (folder / 'locust.log').read_text()
    # The CSV writer's final periodic snapshot can precede completion of one or
    # two in-flight requests. Retain both counts; never rewrite supplied CSVs.
    matches = re.findall(r'^\s*Aggregated\s+(\d+)\s+(\d+)\([0-9.]+%\)\s*\|', text, re.MULTILINE)
    if not matches:
        raise ValueError(f'Missing final Locust console counts: {folder}')
    requests, failures = map(int, matches[-1])
    distribution = read(headers)
    with Path(str(prefix) + '_failures.csv').open() as file:
        errors = list(csv.DictReader(file))
    successes = sum(distribution['per_replica'].values())
    return {'requests_final_console': requests, 'failures_final_console': failures,
            'failure_percent': 100 * failures / requests,
            'csv_requests': int(aggregate['Request Count']), 'csv_failures': int(aggregate['Failure Count']),
            'csv_median_ms': float(aggregate['Median Response Time']),
            'csv_p95_ms': float(aggregate['95%']), 'csv_requests_per_second': float(aggregate['Requests/s']),
            'successful_header_count': successes, 'headers': distribution,
            'replica_success_shares': {name: count / successes for name, count in distribution['per_replica'].items()},
            'final_console_and_headers_agree': requests - failures == successes,
            'failures': errors, 'evidence_directory': str(folder.relative_to(ROOT))}


def summarize():
    completed = read(OUT / 'completed.json')
    cold = read(OUT / 'cold-starts/summary.json')
    loads = {'load-balancing': load_metrics(OUT / 'load-balancing', ROOT / 'results/loadtest', ROOT / 'results/loadtest_headers.json')}
    for label in ('rolling', 'recovery', 'autoscaling-load'):
        loads[label] = load_metrics(OUT / label)
        loads[label]['execution'] = read(OUT / label / 'execution.json')
    loads['load-balancing']['execution'] = read(OUT / 'load-balancing/execution.json')
    interrupted = {p.name: load_metrics(p) for p in sorted(OUT.glob('rolling-interrupted-*'))}
    actions = loads['rolling']['execution']['actions']
    assert [a['action'] for a in actions] == ['update-v2', 'rollback-v1']
    recovery = loads['recovery']['execution']['actions'][0]['result']
    first_idle = read(OUT / 'autoscaling/initial-idle.json')
    loaded = read(OUT / 'autoscaling-load/observations.json')
    last_idle = read(OUT / 'autoscaling/after-load-idle.json')
    scaled = (first_idle[-1]['ready_pods'] == 1 and any(
        o['ready_pods'] >= 2 and any(h.get('status', {}).get('desiredReplicas') == 2
            for h in o['hpa']['items']) for o in loaded) and last_idle[-1]['ready_pods'] == 1)
    final = read(OUT / 'final/resources.json')['items']
    hpa = next(x for x in final if x['kind'] == 'HorizontalPodAutoscaler')
    final_pods = read(OUT / 'final/pods.json')
    download_logs_present = all(
        all(event in (OUT / 'cold-starts' / f"run-{r['run']}" / 'ready' / f"{p['pod']}.log").read_text()
            for event in ('model_download_start', 'model_download_complete', 'model_loaded'))
        for r in cold['runs'] for p in r['pods'])
    checks = {
        'ingress_http_200_initially': read(OUT / 'ingress-probe.json')['status'] == 200,
        'no_ready_endpoints_while_loading': all(r['no_ready_endpoints_observed'] for r in cold['runs']),
        'three_cold_starts_with_download_logs': len(cold['runs']) == 3 and download_logs_present,
        'hpa_min1_max2_target70': hpa['spec']['minReplicas'] == 1 and hpa['spec']['maxReplicas'] == 2
            and hpa['spec']['metrics'][0]['resource']['target']['averageUtilization'] == 70,
        'hpa_observed_1_to_2_to_1': scaled,
        'v2_rollout_and_v1_rollback_verified': actions[0]['result']['version_verified'] == 'v2'
            and actions[1]['result']['version_verified'] == 'v1',
        'rolling_failure_at_most_0_5_percent': loads['rolling']['failure_percent'] <= 0.5,
        'recovery_restores_two_replicas': recovery['replicas_restored'] == 2,
        'recovery_failure_at_most_2_percent': loads['recovery']['failure_percent'] <= 2,
        'both_replicas_at_least_30_percent': len(loads['load-balancing']['replica_success_shares']) == 2
            and all(v >= 0.30 for v in loads['load-balancing']['replica_success_shares'].values()),
    }
    test_text = (OUT / 'unit-tests-resumed.log').read_text()
    count = int(re.search(r'(\d+) passed', test_text)[1])
    summary = {'unit_tests_passed': count, 'cold_starts': cold, 'loads': loads,
               'interrupted_original_runs': interrupted, 'rubric_checks': checks,
               'unmet_checks': [k for k, v in checks.items() if not v],
               'recovery': recovery, 'final_ready_replicas': len(final_pods),
               'final_hpa': hpa, 'final_probe': completed['final_version_probe']}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    lines = ['# Task 4 measured results', '',
        'The existing k3d cluster, SeaweedFS namespace/PV, model weights, datasets and Task 1–3 evidence were preserved. The default kubectl context was unset; project API access works with `export KUBECONFIG="$PWD/.local/kubeconfig"` at https://127.0.0.1:6550. Plain kubectl otherwise falls back to localhost:8080, now the application Ingress, and cannot perform API discovery.', '',
        '## Deployment, probes and cold starts', '',
        'Two replicas were initially deployed in app, with a Secret, Service and Traefik Ingress. Each Pod requests 250m CPU / 512 MiB and is limited to 1 CPU / 1 GiB. Liveness uses /healthz; readiness uses /readyz. maxUnavailable=0, maxSurge=1 and a 5-second preStop delay support graceful changes. The existing k3d load balancer received a port mapping for 127.0.0.1:8080 to port 80; no cluster recreation was used.',
        'The three already completed cold-start experiments were reused without repetition. Every run deleted only app Pods, observed zero Ready Service endpoints while models loaded, and saved real S3 download/checksum/load logs.', '',
        '| Run | Individual Pod creation→Ready times (s) | Run median (s) |', '|---|---|---:|']
    for r in cold['runs']:
        lines.append(f"| {r['run']} | {', '.join(str(p['seconds']) for p in r['pods'])} | {r['median_seconds']:.1f} |")
    lines += ['', f"Median of the three run medians: **{cold['median_of_run_medians_seconds']:.1f} seconds**. Median across all six individual Pod measurements: {cold['all_six_pod_median_seconds']:.1f} seconds. These include scheduling, startup and actual model downloads, using Kubernetes creation and Ready condition timestamps.", '',
        '## Unmodified Locust workload through Ingress', '',
        'All runs used the supplied tools/locustfile.py with four users, spawn rate four, two minutes and http://localhost:8080. The load-balancing run used the specified results/loadtest CSV prefix. No commands or ground-truth labels were replaced to avoid failures.', '',
        '| Run | Final requests | Failures | Failure rate | CSV median (ms) | CSV p95 (ms) | CSV req/s |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name, r in loads.items():
        lines.append(f"| {name} | {r['requests_final_console']} | {r['failures_final_console']} | {r['failure_percent']:.3f}% | {r['csv_median_ms']:.0f} | {r['csv_p95_ms']:.0f} | {r['csv_requests_per_second']:.3f} |")
    lines += ['', 'Counts/rates above use the final Locust console totals; latency and throughput are the supplied CSV values. Periodic CSV snapshots may omit the final one or two in-flight completions. Both originals are retained, and summary.json explicitly records both counts plus successful header totals.', '',
        'The preserved baseline returned exit code 1 due to four HTTP 500 responses. Its final console has 378 requests and its CSV snapshot has 377; successful headers total 374. Replica counts are:', '']
    for pod, n in loads['load-balancing']['headers']['per_replica'].items():
        lines.append(f"- {pod}: {n} successful responses ({100 * loads['load-balancing']['replica_success_shares'][pod]:.2f}%).")
    lines += ['', 'Both exceed the 30% requirement. The exact startup state had two Ready replicas; HPA was applied afterward so the controlled balancing/rollout/recovery experiments retained two replicas.', '',
        '## Rollout, rollback and recovery', '',
        'The interrupted original experiment did deploy v2, but its one-shot assertion incorrectly required HTTP 200 from a command for which v2 generated an invalid frame. The actual 500 carried X-Model-Version=v2. The original logs/CSVs remain in rolling-interrupted-*; its rollback did not execute.',
        'The corrected verifier waits for Ingress readiness and three consecutive matching version headers, retaining every observation. An exact invalid_model_output response proves version identity but is explicitly counted as a model rejection, not successful inference. The real Locust 500s remain failures. Unexpected errors or wrong/stale headers do not pass verification.',
        'A fresh controlled run changed MODEL_URI and MODEL_VERSION from v1 to v2 and executed kubectl rollout undo under the same load, confirming v1 headers afterward. Its HTTP failure rate is shown above; **the ≤0.5% rolling-update criterion is not met**. Model output validation accounts for the recorded HTTP 500s; the code does not weaken schema checks, fabricate labels, repair model text or alter trained weights.',
        f"During recovery, {recovery['deleted_pod']} was deleted under load. The Deployment automatically restored two Ready replicas in **{recovery['replacement_ready_seconds']:.3f} seconds**, without manual replacement/scaling.", '',
        'Task 2 raw JSON validity is not strict schema validity: its saved V066 output has intent datetime_set, outside the permitted eight. The existing Task 2 strict-extraction provenance already counted only 99/100 valid frames. A separate one-command local v2 diagnostic emits repeated/duplicate fields for the rollout probe; it is labelled as a local diagnostic, not a captured server completion. These genuine model limitations explain why correct HTTP 500 validation can miss availability targets.', '',
        '## Autoscaling and rubric status', '',
        'The HPA is autoscaling/v2 with min=1, max=2 and 70% CPU target; it uses a 60-second downscale stabilization window. Actual idle/load/idle observations show one→two→one Ready replicas. Final state has one Ready v1 replica and the HPA remains active. CPU and memory samples, HPA status/events and Pod logs are retained. A single laptop/node is one failure domain; this does not demonstrate resilience across physical machines.', '',
        '| Check | Measured outcome |', '|---|---|']
    lines += [f"| {name} | {'met' if value else 'NOT MET'} |" for name, value in checks.items()]
    lines += ['', f'{count} unit tests pass (one opt-in legacy S3 test skipped). Task 3 remains committed independently at 4b79c23. No model training, teacher labelling, dataset/script edits, bucket deletion or storage restart was performed for this continuation.',
        'Remaining measured Task 4 gaps: ' + ', '.join(summary['unmet_checks']) + '. Improving the trained model/decoding quality would require separately authorized work and a new verified version; no such alteration was made here. Earlier GitHub Release publication also remains pending. All failures, including the interrupted attempt and nonzero Locust exits, are retained.']
    (ROOT / 'report/task4-results.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'unit_tests_passed': count, 'rubric_checks': checks,
                      'unmet_checks': summary['unmet_checks']}, indent=2))
    return summary


if __name__ == '__main__':
    summarize()
