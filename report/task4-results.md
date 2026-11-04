# Task 4 measured results

The existing k3d cluster, SeaweedFS namespace/PV, model weights, datasets and Task 1–3 evidence were preserved. The default kubectl context was unset; project API access works with `export KUBECONFIG="$PWD/.local/kubeconfig"` at https://127.0.0.1:6550. Plain kubectl otherwise falls back to localhost:8080, now the application Ingress, and cannot perform API discovery.

## Deployment, probes and cold starts

Two replicas were initially deployed in app, with a Secret, Service and Traefik Ingress. Each Pod requests 250m CPU / 512 MiB and is limited to 1 CPU / 1 GiB. Liveness uses /healthz; readiness uses /readyz. maxUnavailable=0, maxSurge=1 and a 5-second preStop delay support graceful changes. The existing k3d load balancer received a port mapping for 127.0.0.1:8080 to port 80; no cluster recreation was used.
The three already completed cold-start experiments were reused without repetition. Every run deleted only app Pods, observed zero Ready Service endpoints while models loaded, and saved real S3 download/checksum/load logs.

| Run | Individual Pod creation→Ready times (s) | Run median (s) |
|---|---|---:|
| 1 | 5.0, 5.0 | 5.0 |
| 2 | 6.0, 4.0 | 5.0 |
| 3 | 4.0, 4.0 | 4.0 |

Median of the three run medians: **5.0 seconds**. Median across all six individual Pod measurements: 4.5 seconds. These include scheduling, startup and actual model downloads, using Kubernetes creation and Ready condition timestamps.

## Unmodified Locust workload through Ingress

All runs used the supplied tools/locustfile.py with four users, spawn rate four, two minutes and http://localhost:8080. The load-balancing run used the specified results/loadtest CSV prefix. No commands or ground-truth labels were replaced to avoid failures.

| Run | Final requests | Failures | Failure rate | CSV median (ms) | CSV p95 (ms) | CSV req/s |
|---|---:|---:|---:|---:|---:|---:|
| load-balancing | 378 | 4 | 1.058% | 1100 | 2000 | 3.332 |
| rolling | 308 | 24 | 7.792% | 1100 | 4500 | 2.566 |
| recovery | 320 | 3 | 0.938% | 1400 | 2600 | 2.681 |
| autoscaling-load | 356 | 3 | 0.843% | 1600 | 2300 | 2.982 |

Counts/rates above use the final Locust console totals; latency and throughput are the supplied CSV values. Periodic CSV snapshots may omit the final one or two in-flight completions. Both originals are retained, and summary.json explicitly records both counts plus successful header totals.

The preserved baseline returned exit code 1 due to four HTTP 500 responses. Its final console has 378 requests and its CSV snapshot has 377; successful headers total 374. Replica counts are:

- command-parser-594c8bd455-wdqlr: 188 successful responses (50.27%).
- command-parser-594c8bd455-jnzfg: 186 successful responses (49.73%).

Both exceed the 30% requirement. The exact startup state had two Ready replicas; HPA was applied afterward so the controlled balancing/rollout/recovery experiments retained two replicas.

## Rollout, rollback and recovery

The interrupted original experiment did deploy v2, but its one-shot assertion incorrectly required HTTP 200 from a command for which v2 generated an invalid frame. The actual 500 carried X-Model-Version=v2. The original logs/CSVs remain in rolling-interrupted-*; its rollback did not execute.
The corrected verifier waits for Ingress readiness and three consecutive matching version headers, retaining every observation. An exact invalid_model_output response proves version identity but is explicitly counted as a model rejection, not successful inference. The real Locust 500s remain failures. Unexpected errors or wrong/stale headers do not pass verification.
A fresh controlled run changed MODEL_URI and MODEL_VERSION from v1 to v2 and executed kubectl rollout undo under the same load, confirming v1 headers afterward. Its HTTP failure rate is shown above; **the ≤0.5% rolling-update criterion is not met**. Model output validation accounts for the recorded HTTP 500s; the code does not weaken schema checks, fabricate labels, repair model text or alter trained weights.
During recovery, command-parser-594c8bd455-2rm5b was deleted under load. The Deployment automatically restored two Ready replicas in **6.863 seconds**, without manual replacement/scaling.

Task 2 raw JSON validity is not strict schema validity: its saved V066 output has intent datetime_set, outside the permitted eight. The existing Task 2 strict-extraction provenance already counted only 99/100 valid frames. A separate one-command local v2 diagnostic emits repeated/duplicate fields for the rollout probe; it is labelled as a local diagnostic, not a captured server completion. These genuine model limitations explain why correct HTTP 500 validation can miss availability targets.

## Autoscaling and rubric status

The HPA is autoscaling/v2 with min=1, max=2 and 70% CPU target; it uses a 60-second downscale stabilization window. Actual idle/load/idle observations show one→two→one Ready replicas. Final state has one Ready v1 replica and the HPA remains active. CPU and memory samples, HPA status/events and Pod logs are retained. A single laptop/node is one failure domain; this does not demonstrate resilience across physical machines.

| Check | Measured outcome |
|---|---|
| ingress_http_200_initially | met |
| no_ready_endpoints_while_loading | met |
| three_cold_starts_with_download_logs | met |
| hpa_min1_max2_target70 | met |
| hpa_observed_1_to_2_to_1 | met |
| v2_rollout_and_v1_rollback_verified | met |
| rolling_failure_at_most_0_5_percent | NOT MET |
| recovery_restores_two_replicas | met |
| recovery_failure_at_most_2_percent | met |
| both_replicas_at_least_30_percent | met |

95 unit tests pass (one opt-in legacy S3 test skipped). Task 3 remains committed independently at 4b79c23. No model training, teacher labelling, dataset/script edits, bucket deletion or storage restart was performed for this continuation.
Remaining measured Task 4 gaps: rolling_failure_at_most_0_5_percent. Improving the trained model/decoding quality would require separately authorized work and a new verified version; no such alteration was made here. Earlier GitHub Release publication also remains pending. All failures, including the interrupted attempt and nonzero Locust exits, are retained.
