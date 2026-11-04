#!/usr/bin/env python3
"""Task 7: derive measured performance and explicit hypothetical costs from evidence."""
import csv
from decimal import Decimal, ROUND_FLOOR
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/task7'


def cost_per_1000(replicas, cpu_limit, memory_gib, rps, cpu_rate, memory_rate):
    values = [Decimal(str(x)) for x in (replicas, cpu_limit, memory_gib, rps, cpu_rate, memory_rate)]
    n, cpu, memory, throughput, cpu_price, memory_price = values
    if throughput <= 0:
        raise ValueError('Measured throughput must be positive')
    per_replica = cpu * cpu_price + memory * memory_price
    hourly = n * per_replica
    requests_hour = throughput * Decimal(3600)
    return {'per_replica_hour': per_replica, 'all_replicas_hour': hourly,
            'requests_per_hour': requests_hour, 'cost_per_1000': hourly / requests_hour * 1000}


def error_budget(total, failures, target='0.99'):
    fractional = (Decimal(1) - Decimal(target)) * total
    whole = int(fractional.to_integral_value(rounding=ROUND_FLOOR))
    return {'target_success_fraction': str(target), 'requests': total, 'failures': failures,
            'fractional_failure_budget': str(fractional), 'whole_failure_budget': whole,
            'failures_over_budget': max(0, failures - whole),
            'whole_budget_consumed_percent': None if not whole else 100 * failures / whole,
            'success_percent': 100 * (total - failures) / total,
            'slo_met': failures <= whole}


def pod_samples(path):
    collected = {}
    for line in Path(path).read_text().splitlines():
        parts = line.split()
        if len(parts) != 3 or not parts[0].startswith('command-parser-'):
            continue
        cpu = Decimal(parts[1][:-1]) if parts[1].endswith('m') else Decimal(parts[1]) * 1000
        size = re.fullmatch(r'([0-9.]+)(Ki|Mi|Gi)', parts[2])
        if not size:
            raise ValueError('Unexpected kubectl top memory unit')
        memory_mib = Decimal(size[1]) * {'Ki': Decimal(1)/1024, 'Mi': Decimal(1), 'Gi': Decimal(1024)}[size[2]]
        collected.setdefault(parts[0], []).append((float(cpu), float(memory_mib)))
    if not collected:
        raise ValueError('No measured per-Pod CPU/memory samples')
    return {name: {'samples': len(rows), 'cpu_millicores_min': min(x[0] for x in rows),
                  'cpu_millicores_max': max(x[0] for x in rows),
                  'memory_mib_min': min(x[1] for x in rows), 'memory_mib_max': max(x[1] for x in rows)}
            for name, rows in collected.items()}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    task4 = json.loads((ROOT / 'results/task4/summary.json').read_text())
    baseline = task4['loads']['load-balancing']
    card = json.loads((ROOT / 'data/rate_card.json').read_text())
    resources = json.loads((ROOT / 'results/task4/load-balancing/before/resources.json').read_text())['items']
    deployment = next(x for x in resources if x['kind'] == 'Deployment')
    limit = deployment['spec']['template']['spec']['containers'][0]['resources']['limits']
    assert limit == {'cpu': '1', 'memory': '1Gi'} and deployment['spec']['replicas'] == 2
    with (ROOT / 'results/loadtest_stats.csv').open() as file:
        csv_row = next(r for r in csv.DictReader(file) if r['Name'] == 'Aggregated')
    cost = cost_per_1000(2, 1, 1, csv_row['Requests/s'], card['vcpu_hour'], card['gib_memory_hour'])
    budget = error_budget(baseline['requests_final_console'], baseline['failures_final_console'])
    pods = pod_samples(ROOT / 'results/task4/load-balancing/top-samples.txt')
    result = {'source_run': 'Task 4 standard fixed-two-replica load-balancing test; no extra load test needed',
              'performance': baseline, 'per_pod_samples': pods,
              'cold_start_run_medians_seconds': [r['median_seconds'] for r in task4['cold_starts']['runs']],
              'cold_start_median_seconds': task4['cold_starts']['median_of_run_medians_seconds'],
              'pricing': card, 'cost_estimate_inr': {k: str(v) for k,v in cost.items()},
              'billing_assumptions': {'running_replicas': 2, 'cpu_limit_each': 1, 'memory_limit_gib_each': 1,
                  'included': 'The two app replicas specified by the rate card; excludes storage/control plane/Ollama'},
              'slo': budget, 'local_performance_thresholds': {
                  'error_rate_at_most_1_percent': baseline['failure_percent'] <= 1,
                  'p95_at_most_5000_ms': baseline['csv_p95_ms'] <= 5000}}
    (OUT / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    lines = ['# Task 7: performance, estimated cost and review', '',
        'All performance values below are measurements from the existing standard Task 4 baseline through Traefik: four users, spawn rate four, two minutes, unchanged tools/locustfile.py. No additional load run or model training was needed. Raw files remain results/loadtest_*.csv, results/loadtest_headers.json and results/task4/load-balancing/.', '',
        f"- p50/median: **{baseline['csv_median_ms']:.0f} ms**; p95: **{baseline['csv_p95_ms']:.0f} ms**.",
        f"- Measured Locust throughput: **{baseline['csv_requests_per_second']:.12f} requests/s**.",
        f"- Final console totals: **{baseline['requests_final_console']} requests, {baseline['failures_final_console']} failures**, error rate **{baseline['failure_percent']:.6f}%**. All four failures were HTTP 500 validation rejections.",
        '- The CSV periodic snapshot has 377 requests, while the final console has 378; successful header counts total 374. These originals are retained, not reconciled by editing measurements. Latency/throughput come from CSV; final error percentage uses the complete console counts.',
        '- Cold-start run medians: **5.0, 5.0, 4.0 s**, median **5.0 s**. All six individual Pod measurements and download logs remain in Task 4 evidence.', '',
        '## Per-Pod resources during that run', '',
        'These are sampled kubectl top working-set observations, not a continuous peak or a memory-limit allocation. The original time series is results/task4/load-balancing/top-samples.txt.', '',
        '| Pod | Samples | CPU range (m) | Memory range (MiB) |', '|---|---:|---:|---:|']
    for name,p in pods.items():
        lines.append(f"| {name} | {p['samples']} | {p['cpu_millicores_min']:.0f}–{p['cpu_millicores_max']:.0f} | {p['memory_mib_min']:.0f}–{p['memory_mib_max']:.0f} |")
    lines += ['', '## Hypothetical cost calculation (INR)', '',
        'Prices are exactly the supplied hypothetical rate card; no real cloud charge is incurred. Bill limits, not requests or observed consumption. The controlled baseline had exactly two running app replicas, each limited to 1 vCPU and 1 GiB.', '',
        f"1. Per replica per hour = (1 × ₹{card['vcpu_hour']:.2f}) + (1 × ₹{card['gib_memory_hour']:.2f}) = **₹{cost['per_replica_hour']}**.",
        f"2. All replicas per hour = 2 × ₹{cost['per_replica_hour']} = **₹{cost['all_replicas_hour']}**.",
        f"3. Requests per hour = {csv_row['Requests/s']} × 3,600 = **{cost['requests_per_hour']}**.",
        f"4. Cost per 1,000 = (₹{cost['all_replicas_hour']} / {cost['requests_per_hour']}) × 1,000 = **₹{cost['cost_per_1000']:.8f}** (approximately ₹{cost['cost_per_1000']:.4f}).", '',
        'This extrapolates the measured rate over an hour with two replicas throughout. It counts all served request attempts, including HTTP 500 responses, and excludes SeaweedFS/control-plane/teacher costs because the supplied exercise prices the app replicas. It is an estimate and a stated boundary, not measured expenditure.', '',
        '## SLO and request-based error budget', '',
        'SLO: at least **99% of requests succeed (HTTP 200)** within one complete standard two-minute load-test run.',
        f"For N=378, the fractional failure allowance is 0.01 × 378 = **{budget['fractional_failure_budget']} requests**. Because requests are indivisible, the operational budget is **{budget['whole_failure_budget']} failed requests** (floor).",
        f"Actual consumption is **4 failures**, or **{budget['whole_budget_consumed_percent']:.2f}%** of the whole-request budget, exceeding it by **1 request**. Success = 374/378 = **{budget['success_percent']:.6f}%**. The SLO is **not met**.",
        'The local ≤1% error threshold is likewise not met, while p95 ≤5,000 ms is met. This does not establish performance on the assessor\'s hardware. The rolling-update ≤0.5% gap from Task 4 also remains unresolved.', '',
        '## Six-row measured review', '',
        '| Component or concern | Evidence (measured number) | Limitation found | Proposed improvement |', '|---|---|---|---|']
    peak_cpu = max(p['cpu_millicores_max'] for p in pods.values())
    peak_mem = max(p['memory_mib_max'] for p in pods.values())
    lines += [
        '| Data and storage | 2,225 of 3,000 teacher records kept; both model versions verified by SHA-256 | Filtering discards 775 records; local storage shares one machine | Monitor rejection bias and add replicated/versioned storage |',
        '| Model quality | V1 raw JSON validity 100%, intent 80%, full-frame 26%; strict extraction 99/100 | Syntactic validity does not imply a permitted intent or correct slots | Evaluate constrained decoding/a new model version without gold-frame fallbacks |',
        f"| Latency and throughput | p50 1,100 ms; p95 2,000 ms; {baseline['csv_requests_per_second']:.3f} req/s | CPU-bound inference at capped replicas | Profile token generation and test batching before changing limits |",
        f'| Resource utilisation | Sampled per-Pod maxima {peak_cpu:.0f}m CPU and {peak_mem:.0f} MiB | Near one-core CPU limit; samples can miss short memory peaks | Profile sustained CPU and use continuous resource telemetry |',
        '| Reliability and recovery | Cold-start median 5.0 s; two replicas restored in 6.863 s; rolling errors 7.792% | Model validation failures breach rollout error budget; one physical failure domain | Validate candidate models before promotion and use multiple physical nodes |',
        f"| Security and cost | Task 4 scan: 0 known generated-key findings; estimated ₹{cost['cost_per_1000']:.4f}/1,000 | Known-key scan is narrower than a full secret scan; prices are hypothetical | Enforce CI secret scanning, least-privilege S3 access and measured production pricing |", '',
        'Each improvement is proposed, not claimed implemented or benchmarked. Secret scanning/CI publication evidence is tracked separately in Task 6.']
    (ROOT / 'report/task7-results.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'cost_estimate_inr': result['cost_estimate_inr'], 'slo': budget,
                      'per_pod_samples': pods, 'thresholds': result['local_performance_thresholds']}, indent=2))


if __name__ == '__main__':
    main()
