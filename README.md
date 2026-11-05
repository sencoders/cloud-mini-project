# CS3081 command-parsing mini project

A native Ollama phi3.5 teacher labels commands; CPU-only EleutherAI/pythia-70m
learns the teacher responses. SeaweedFS stores data and model artifacts in k3d.
FastAPI serves the student through Traefik, with probes, two-replica experiments
and an HPA. `ASSIGNMENT.pdf` is authoritative. AI assistance and verification are
fully disclosed in [AI_USE.md](AI_USE.md).

## Verified local results

| Item | Measured result |
|---|---|
| Teacher data | 3,000 IDs accounted for; 2,225 cleaned records; 775 rejected/duplicates |
| Training | First 1,500 cleaned records, CPU only; V1 147.99 s; V2 additional epoch 50.98 s |
| V1 validation | JSON 100%, intent 80%, date 66%, time 70%, place 77%, full frame 26% |
| Docker | Image 1.33 GB; 50/50 sequential requests at 1 CPU / 1 GiB; peak 806.43 MiB; no OOM |
| Standard load | p50 1,100 ms; p95 2,000 ms; 3.33196 requests/s; failures 4/378 (1.058%) |
| Load balancing | Two Ready replicas served 188 and 186 successful responses |
| Cold starts | Run medians 5.0, 5.0, 4.0 s; overall median 5.0 s |
| Recovery | Two Ready replicas restored in 6.863 s; 3/320 failures (0.938%) |
| Rolling V1→V2→V1 | Version changes verified; 24/308 failures (7.792%) |
| HPA | Observed 1→2→1; min 1, max 2, CPU target 70% |
| Networking | Supplied simulator 6/6; 25 focused networking tests |
| Unit suite | 129 passed, 1 optional live-S3 test skipped |
| Estimated cost | INR 0.6586 per 1,000 attempts at the measured two-replica rate |

The **rolling ≤0.5% error criterion is unmet**. The **baseline ≤1% error criterion
and 99% success SLO are unmet**; p95 ≤5,000 ms passes locally. Model-output HTTP
500s remain failures. The supplied scorer's JSON-shape validity differs from strict
eight-intent schema validation (V1 99/100). There is no ground-truth fallback.
Single-laptop results do not establish cross-machine fault tolerance or hidden-test
performance. CSV snapshot counts and final console counts differ by one request;
originals and the calculation boundaries are preserved in the reports.

## Setup and deployment

System prerequisites: Python 3.12, Docker, k3d, kubectl and GitHub CLI (`gh`).
Ollama stays native on macOS; `phi3.5:latest` is needed only for teacher operations.
Training and serving use CPU only. No second teacher or embedded weights enter the
service image.

Fresh bootstrap requires a **verified published Release containing both versions**:
set `MODEL_RELEASE_REPOSITORY` to the real owner/repository and
`MODEL_RELEASE_TAG` to its model Release tag; authenticate `gh` for a private repo.
Then, in at most three commands:

```sh
python3.12 -m venv .venv312
.venv312/bin/pip install -r requirements-service-dev.txt
make up
```

The fresh path verifies Release archive/member hashes, creates the cluster/storage,
builds/imports worker and service images, restores models to S3 and deploys the app,
Ingress and HPA. It never retrains or regenerates labels. Missing Release settings
fail before cluster creation. **Fresh-clone bootstrap has not been verified end to
end**; do not infer that from successful checks on the existing deployment.

On the existing workspace, `make up` verifies healthy storage and app while
preserving data and replica policy. See `results/task6/make-up.log`.

```sh
export KUBECONFIG="$PWD/.local/kubeconfig"
kubectl get pods,deploy,svc,ingress,hpa -n app
curl http://localhost:8080/readyz
curl -H 'Content-Type: application/json' -d '{"text":"what is the weather in london"}' http://localhost:8080/parse
```

The Kubernetes API is `https://127.0.0.1:6550`; port 8080 is the app Ingress.
S3 is exposed on `http://127.0.0.1:8333`. Credentials and kubeconfig live only in
ignored `.local/` files and Kubernetes Secrets, never in source or Release assets.
The existing cluster is intentionally preserved during publication.

## Tests and evidence

```sh
make test
make network-check
make performance-report
.venv312/bin/pip install ruff==0.14.4
make lint
```

The optional live-storage test is enabled with `TASK1_S3_TEST=1 make test` when S3
credentials and endpoint are configured. A skipped integration test is not reported
as passed. `make performance-report` recomputes cost/SLO from preserved genuine
measurements; it does not rerun load tests.

All original data, instructor tools and assignment bytes are unchanged, verified
against `results/supplied-files.sha256.json`. Logs, predictions, losses, actual
Locust CSVs, resource observations, failures and command outputs are under results/.
Some genuine logs retain local workspace paths; these are not portable commands.
Detailed task reports distinguish historical milestone checks from current status.

## Training and storage

Task 1 operations are `make smoke`, `make label`, `make status`, then `make clean`
after all IDs finish. The Jobs use deterministic line-number modulo sharding and
restart-safe S3 checkpoints. Run them only when intentionally reproducing Task 1;
the existing labels and genuine evidence are already complete.

`training/config.yaml` pins seed, learning rate, batch size, epochs, sequence length,
CPU settings, exact versions and source checksums. Training uses the first 1,500
cleaned records in ID order and masks prompt/padding loss. Validation is never
training data. Smoke artifacts cannot overwrite full artifacts.

```sh
make train SUBSET=50
make train VERSION=v1
make train VERSION=v2
make upload-model VERSION=v1
make upload-model VERSION=v2
```

These commands reproduce training; **do not rerun completed training for publication**.
Teacher replies remain unmodified. Cleaned data is `s3://datasets/v1/train.jsonl`,
SHA-256 `1865c9ddc2a723247e96336c0ef966cd3b669aa904ae03d29f77ef4fe92b03e5`.
Models/tokenizers are `s3://models/v1/` and `s3://models/v2/`; committed public
manifests are `models/v1/model.sha256` and `models/v2/model.sha256`.
Actual weights and release archives stay in ignored `.local/` and object storage.

## Service and Kubernetes operations

```sh
make service-build
make service-test
make app-status
```

`make service-test` performs the real constrained Docker test and retains new
run-specific evidence. It reads existing Secret credentials into a private env
file. Service startup downloads/checks every artifact. `/healthz` is liveness;
`/readyz` is 503 until loading completes. `/parse` success returns exactly four
keys and sets `X-Model-Version` and actual-hostname `X-Served-By` headers. Invalid
output, including `FAULT_INJECT=1`, returns exactly HTTP 500
`{"error":"invalid_model_output"}`.

`MODEL_URI`, `MODEL_VERSION`, `S3_ENDPOINT`, `MAX_NEW_TOKENS` and `FAULT_INJECT`
configure serving. Credentials come explicitly from Secret-derived environment
variables. `cluster/app.yaml` initially deploys two replicas with probes/limits;
`cluster/hpa.yaml` manages min 1/max 2 afterward. Existing load/cold-start experiments
should not be repeated for publication. See `scripts/task4.py` for resumable
experiment commands and guards.

## Shutdown

```sh
make down-dry-run
```

This prints the tested command `k3d cluster delete command-parser`.
**`make down` actually deletes the cluster and local persistent storage**. It has
not been executed for verification on this preserved deployment. Export necessary
data before an intentional shutdown; `scripts/storage_snapshot.py` supports
verified export/restore. Test destructive teardown on a separate disposable cluster.

## CI, releases and submission

Verified private repository: https://github.com/sencoders/cloud-mini-project

- Published V1: https://github.com/sencoders/cloud-mini-project/releases/tag/models-v1-v2
  (V1 archive/member/version checks pass; V2 archive upload is blocked by recorded transport timeouts).
- Passing normal CI: https://github.com/sencoders/cloud-mini-project/actions/runs/42029372903
- Deliberate untrained-model gate failure: https://github.com/sencoders/cloud-mini-project/actions/runs/42030357782
  (100 evaluated records; 0% validity; unchanged 95% gate; other jobs passed).

The original failed run stopped at Release download with `release not found` after
a network-interrupted upload. The fix was verified asset publication; training,
weights, evaluation data, workflow code and the quality threshold were unchanged.
Full logs, predictions, score reports and Release verification are in results/publication/.


[Release instructions](docs/releases.md) describe the actual archive boundaries,
checksums and publication procedure. CI orders lint → unit tests → actual Release
download/CPU evaluation → supplied `score.py --min-validity 95` → Gitleaks.
The separate bad-model workflow evaluates the real untrained Pythia model.
Set repository variable `MODEL_RELEASE_TAG` to the verified model Release tag.
Remote execution evidence belongs in `results/publication/`; historical Task 6
files explicitly record what was unverified when they were produced.

Gitleaks retains all default rules with one exact **public Docker signing
fingerprint** exception, documented in `results/task6/secret-scan-notes.md`.
Original diagnostic findings are retained. No genuine secret is allowlisted.
[Publication audit and file classification](docs/publication-audit.md) records the
repository/Release/separate-reflection boundaries and outstanding submission items.

The [seven-page report](report/report.pdf) has one section per task. Rebuild with
`requirements-report.txt` and `.venv312/bin/python report/build_report.py`.
The mandatory three-page **handwritten** reflection must be supplied by the student
as exactly `<roll_number>.pdf`, with name, roll number and the real GitHub link.
No `final` tag is created during this publication stage.

- [Task 1 design](report/task1-design.md) and [results](report/task1-results.md)
- [Task 2 results](report/task2-results.md) and [distillation explanation](docs/distillation.md)
- [Task 3 results](report/task3-results.md)
- [Task 4 results](report/task4-results.md)
- [Task 5 subnetting and NACL explanation](network/subnets.md)
- [Task 6 local checks](report/task6-results.md)
- [Task 7 performance/cost/SLO/review](report/task7-results.md)

Dataset attribution: SLURP, Bastianelli et al., EMNLP 2020, CC BY 4.0,
https://github.com/pswietojanski/slurp. Base student: EleutherAI/pythia-70m, Apache 2.0.
