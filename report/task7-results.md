# Task 7: performance, estimated cost and review

All performance values below are measurements from the existing standard Task 4 baseline through Traefik: four users, spawn rate four, two minutes, unchanged tools/locustfile.py. No additional load run or model training was needed. Raw files remain results/loadtest_*.csv, results/loadtest_headers.json and results/task4/load-balancing/.

- p50/median: **1100 ms**; p95: **2000 ms**.
- Measured Locust throughput: **3.331957779810 requests/s**.
- Final console totals: **378 requests, 4 failures**, error rate **1.058201%**. All four failures were HTTP 500 validation rejections.
- The CSV periodic snapshot has 377 requests, while the final console has 378; successful header counts total 374. These originals are retained, not reconciled by editing measurements. Latency/throughput come from CSV; final error percentage uses the complete console counts.
- Cold-start run medians: **5.0, 5.0, 4.0 s**, median **5.0 s**. All six individual Pod measurements and download logs remain in Task 4 evidence.

## Per-Pod resources during that run

These are sampled kubectl top working-set observations, not a continuous peak or a memory-limit allocation. The original time series is results/task4/load-balancing/top-samples.txt.

| Pod | Samples | CPU range (m) | Memory range (MiB) |
|---|---:|---:|---:|
| command-parser-594c8bd455-jnzfg | 39 | 4–998 | 305–430 |
| command-parser-594c8bd455-wdqlr | 39 | 6–998 | 305–413 |

## Hypothetical cost calculation (INR)

Prices are exactly the supplied hypothetical rate card; no real cloud charge is incurred. Bill limits, not requests or observed consumption. The controlled baseline had exactly two running app replicas, each limited to 1 vCPU and 1 GiB.

1. Per replica per hour = (1 × ₹3.50) + (1 × ₹0.45) = **₹3.95**.
2. All replicas per hour = 2 × ₹3.95 = **₹7.90**.
3. Requests per hour = 3.331957779810104 × 3,600 = **11995.048007316374400**.
4. Cost per 1,000 = (₹7.90 / 11995.048007316374400) × 1,000 = **₹0.65860512** (approximately ₹0.6586).

This extrapolates the measured rate over an hour with two replicas throughout. It counts all served request attempts, including HTTP 500 responses, and excludes SeaweedFS/control-plane/teacher costs because the supplied exercise prices the app replicas. It is an estimate and a stated boundary, not measured expenditure.

## SLO and request-based error budget

SLO: at least **99% of requests succeed (HTTP 200)** within one complete standard two-minute load-test run.
For N=378, the fractional failure allowance is 0.01 × 378 = **3.78 requests**. Because requests are indivisible, the operational budget is **3 failed requests** (floor).
Actual consumption is **4 failures**, or **133.33%** of the whole-request budget, exceeding it by **1 request**. Success = 374/378 = **98.941799%**. The SLO is **not met**.
The local ≤1% error threshold is likewise not met, while p95 ≤5,000 ms is met. This does not establish performance on the assessor's hardware. The rolling-update ≤0.5% gap from Task 4 also remains unresolved.

## Six-row measured review

| Component or concern | Evidence (measured number) | Limitation found | Proposed improvement |
|---|---|---|---|
| Data and storage | 2,225 of 3,000 teacher records kept; both model versions verified by SHA-256 | Filtering discards 775 records; local storage shares one machine | Monitor rejection bias and add replicated/versioned storage |
| Model quality | V1 raw JSON validity 100%, intent 80%, full-frame 26%; strict extraction 99/100 | Syntactic validity does not imply a permitted intent or correct slots | Evaluate constrained decoding/a new model version without gold-frame fallbacks |
| Latency and throughput | p50 1,100 ms; p95 2,000 ms; 3.332 req/s | CPU-bound inference at capped replicas | Profile token generation and test batching before changing limits |
| Resource utilisation | Sampled per-Pod maxima 998m CPU and 430 MiB | Near one-core CPU limit; samples can miss short memory peaks | Profile sustained CPU and use continuous resource telemetry |
| Reliability and recovery | Cold-start median 5.0 s; two replicas restored in 6.863 s; rolling errors 7.792% | Model validation failures breach rollout error budget; one physical failure domain | Validate candidate models before promotion and use multiple physical nodes |
| Security and cost | Task 4 scan: 0 known generated-key findings; estimated ₹0.6586/1,000 | Known-key scan is narrower than a full secret scan; prices are hypothetical | Enforce CI secret scanning, least-privilege S3 access and measured production pricing |

Each improvement is proposed, not claimed implemented or benchmarked. Secret scanning/CI publication evidence is tracked separately in Task 6.
