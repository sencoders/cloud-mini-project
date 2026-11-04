# Task 1 completed

All **3,000 commands** are accounted for exactly once across two 1,500-record
shards. Cleaning kept **2,225** records: 2 invalid JSON, 2 wrong keys, 526 invalid
intents, 202 invalid slots and 43 duplicates were removed. All **39 tests** pass,
including live S3 checks. Two cleaning runs and offline regeneration agree on
SHA-256 `1865c9ddc2a723247e96336c0ef966cd3b669aa904ae03d29f77ef4fe92b03e5`.

See [measured results](report/task1-results.md), [sharding design](report/task1-design.md),
and [evidence](results/full/). SeaweedFS remains running in `data`; both full-run
Jobs completed in `pipeline`. Native macOS Ollama served both workers. No Task 2
training, remote push, or `final` tag was performed. Setup and shutdown commands
are below. The original student-kit README follows this status note.

---

# Student Kit: Cloud Computing Mini Project

Read the project handout first. It explains every file here.

    data/commands_pool.jsonl     3,000 commands (text only)
    data/validation.jsonl        100 labelled commands, for evaluation only (never train on them)
    data/schema.json             the four keys, the eight intents and the slot rules
    data/rate_card.json          hypothetical prices for the cost exercise
    tools/score.py               python tools/score.py PREDICTIONS data/validation.jsonl [--min-validity 95]
    tools/locustfile.py          pip install locust, then:
                                 locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv results/loadtest
    tools/nacl_sim.py            python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
    network/packets_sample.jsonl six sample packets with expected decisions

score.py and nacl_sim.py need only Python 3 (standard library); run them with -h for help. The load test needs Locust (https://locust.io).

Data: commands from SLURP (Bastianelli et al., EMNLP 2020), licensed CC BY 4.0.
https://github.com/pswietojanski/slurp

---

# Task 1: object storage and parallel teacher labelling

`ASSIGNMENT.pdf` is authoritative. All 15 pages were read; extracted text is in
`results/assignment.txt`. Only Task 1 is implemented here. No Task 2 training has
started. The supplied data, schema, scripts and sample packets are unchanged;
`results/supplied-files.sha256.json` records their checksums.

## Setup on Apple Silicon

Requirements: Docker Desktop running, k3d, kubectl, Python **3.12**, and native macOS
Ollama with `phi3.5:latest` downloaded and serving on port 11434. Both workers use
that one native model server via Docker Desktop's `host.docker.internal`; no model
weights are placed in Kubernetes or in the worker image. Docker Desktop used about
1 GiB for the cluster before labelling; Ollama uses macOS Metal separately.

```sh
python3.12 -m venv .venv312
.venv312/bin/pip install -r requirements-dev.txt
make up
```

`make up` creates the cluster from `cluster/k3d.yaml`, deploys SeaweedFS in `data`,
creates `datasets` and `models`, uploads and downloads `commands_pool.jsonl` to
verify exact bytes, and builds/imports the worker image. It does **not** start
labelling. On an existing cluster use these commands instead of creating it again:

```sh
.venv312/bin/python scripts/task1.py setup
.venv312/bin/python scripts/task1.py build
```

Credentials are randomly generated on first setup, stored only in ignored
`.local/credentials.json` (0600), and injected into Kubernetes Secrets through stdin.
`.local/kubeconfig` is private and ignored too. Do not commit `.local/` or export
Secret YAML into `results/`. Kubeconfig output is deliberately omitted from command
logs. S3 is exposed only at `http://127.0.0.1:8333` on the Mac. The deployment's
readiness probe checks the S3 listener; setup performs the authenticated API check.

SeaweedFS uses a 5 GiB static local PersistentVolume at `/var/lib/seaweedfs-data`
inside the k3d node. This avoids dependence on downloading a dynamic provisioner.
Master, volume and filer metadata live on the mounted volume; `workingDir: /data/recovered`
keeps the default filer database there. The Service publishes internal addresses
before readiness so these components can initialize. This is a single-machine lab,
without hardware fault tolerance. Pod restarts preserve data; deleting the k3d
cluster destroys its node-local data. Export artifacts before `make down`.

## Mandatory five-command smoke test

```sh
make test
make smoke
export KUBECONFIG="$PWD/.local/kubeconfig"
kubectl -n pipeline wait --for=condition=complete job/smoke-json-0 job/smoke-json-1 --timeout=300s
.venv312/bin/python scripts/task1.py status --run smoke
.venv312/bin/python scripts/task1.py clean --run smoke
```

These are five **dataset commands**, the first five physical lines, divided 3/2
between two distinct Jobs. Full launch is gated on five accepted records, complete
ID accounting, a matching prompt/input fingerprint, verified storage, and positive
worker overlap. Do not bypass the gate. Smoke objects are isolated under
`s3://datasets/teacher/smoke-json/`; their cleaned output is under
`s3://datasets/smoke/v1/` and is never used as the full training dataset.

The first smoke attempt exposed explanatory prose in 4/5 replies. Its exact raw
responses, failed cleaning counts and logs are preserved in `results/smoke-attempt1/`
and `s3://datasets/teacher/smoke/`. Enabling Ollama JSON response mode fixed the
transport format; the second smoke accepted 5/5, with two seconds of container
execution overlap. It produced SHA-256
`3f776d1a1b683fa4c233b782746017386e2d1c53b6207c4c7e8e1d15a1098a0a`.
The same checksum was verified after restarting SeaweedFS. JSON mode constrains
format during generation; no generated reply is stripped, repaired or relabelled.

## Full labelling and automatic finalization

After the smoke checks pass:

```sh
make label
caffeinate -i .venv312/bin/python -u scripts/task1.py finish > results/finish.log 2>&1
```

`teacher-0` and `teacher-1` are distinct Kubernetes Jobs in `pipeline`, each with
`SHARD_COUNT=2` and a different `SHARD_INDEX`. They call `phi3.5:latest` with
`temperature=0`, `seed=42`, JSON mode, a 2,048-token context and a 256-token output
limit. The exact prompt is `prompts/teacher_prompt.txt`; model digest and version
are recorded in `results/runtime.json`. No paid API is used.

The completion monitor does not start inference: it observes existing Jobs, saves
logs and snapshots every 30 seconds, detects failed Jobs, then checks all 3,000 IDs,
cleans, uploads and downloads the checksum, and cleans a second time to verify
reproducibility. It writes `report/task1-results.md` only after successful completion.
Keep the Mac awake, Docker running and native Ollama running. `caffeinate -i`
prevents idle sleep while monitoring. If monitoring is interrupted, repeat the
`finish` command; existing Jobs continue independently. A 20-hour monitor timeout
leaves Jobs intact and records an error.

Monitor in another terminal:

```sh
make status
cat results/full/progress.json
cat results/full/concurrency.json
tail -n 30 results/finish.log
kubectl -n pipeline get jobs,pods -o wide
kubectl -n pipeline logs -f job/teacher-0
kubectl -n pipeline logs -f job/teacher-1
kubectl top pods -A
```

`durable_completed` counts successfully checkpointed IDs; final ID accounting is
confirmed only when cleaning succeeds. `results/full/jobs.json`, `pods.json`,
`concurrency.json`, and timestamped logs provide measured concurrency evidence.
Kubernetes workers can overlap even if the native Ollama server internally queues
inference requests. Two worker Pods do not imply two loaded model copies.

## Sharding, retries and recovery

For zero-based physical input line number `n`, worker `i` takes the record iff
`n % SHARD_COUNT == SHARD_INDEX`. With two workers this gives 1,500 records each.
Duplicate command text at different IDs still receives its own genuine teacher
reply; text deduplication happens only during cleaning. Blank input lines and
duplicate source IDs are treated as errors rather than renumbered or discarded.

Every exact reply is saved as `{"id":...,"text":...,"teacher_raw":...}` to a
verified S3 checkpoint at `teacher/progress/shard-I/ID.json`, then included in that
worker's own `teacher/shard-I.jsonl`. Checkpoint and shard writes are read back and
compared byte for byte. On restart, the worker checks its input/prompt/settings
fingerprint and reuses checkpoints, rebuilding its shard in deterministic order.
A configuration change requires a fresh prefix; it cannot silently reuse old labels.

Transient inference errors are logged and retried up to five times with exponential
backoff. Invalid teacher labels are stored unchanged and rejected later, rather
than repeatedly sampled until acceptable. A storage failure stops the worker;
Kubernetes retries the Job up to eight times. Inference can repeat if a process dies
after receiving the reply but before its checkpoint becomes durable. Durable output
uses one object per source ID, and final cleaning rejects missing, repeated,
misplaced or altered source records. This provides restart-safe output accounting,
without claiming transactional exactly-once execution of a remote model request.

If a Job exhausts retries, inspect its saved logs first, fix connectivity/storage,
then recreate only that Job (the saved YAML contains no credentials):

```sh
kubectl -n pipeline delete job teacher-0
kubectl apply -f results/teacher-job-0.yaml
```

Use `teacher-1` and its manifest for the other shard. Existing S3 checkpoints are
retained. Never delete progress objects to recover a run. `make label` is idempotent
for existing Jobs and does not rerun completed Jobs.

## Cleaning and storage paths

```sh
make clean
```

The cleaner reads exactly the two requested shard objects and verifies each against
its expected source IDs/texts before writing a dataset. It refuses partial runs.
Rejection reasons are mutually exclusive, checked in PDF order: (a) invalid JSON,
(b) wrong four keys, (c) intent outside the eight, (d) a non-null slot that is not a
string copied exactly from the command. Strict JSON parsing also rejects duplicate
JSON member names and NaN/Infinity. It does not guess the semantic correctness of
a label or impose extra date/time heuristics. For remaining duplicate command
texts, it keeps the smallest ID. Records are sorted by ID; `teacher_raw` remains
exactly the generated string. Training examples retain `{id,text,teacher_raw}`.
No validation labels enter this process.

| S3 URI | Purpose |
|---|---|
| `s3://datasets/commands_pool.jsonl` | Original 3,000-record input |
| `s3://datasets/teacher/shard-0.jsonl` | Raw even-line shard |
| `s3://datasets/teacher/shard-1.jsonl` | Raw odd-line shard |
| `s3://datasets/teacher/progress/` | Per-ID restart checkpoints and fingerprints |
| `s3://datasets/v1/train.jsonl` | Cleaned records, created after full coverage |
| `s3://datasets/v1/train.sha256` | SHA-256 of exact train.jsonl bytes |
| `s3://datasets/v1/counts.json` | Complete cleaning counts and digest |
| `s3://models/` | Empty bucket reserved for later tasks |

Local exports are in `results/full/`, including raw shards, cleaned records,
rejection IDs/reasons and counts. `input = a + b + c + d + duplicates + kept` is
asserted. `reproducibility.json` records both full cleaning checksums when the
monitor finishes. To verify the downloaded file independently:

```sh
(cd results/full && shasum -a 256 -c train.sha256)
```

Use the progress JSON and logs for current status. Absence of `results/full/counts.json`
means full cleaning has not yet succeeded; do not report a final kept count or use
partial output for training. Generated files change while monitoring is active;
commit completed evidence only after the run finishes.

## Tests and shutdown

```sh
make test
.venv312/bin/python -m compileall -q worker scripts tests
```

The tests cover exact modulo sharding, all PDF rejection rules, deterministic
ordering/deduplication, raw-response preservation, missing/repeated/misplaced IDs,
S3 corruption and access errors, retry handling, restart after a checkpoint write,
configuration drift, and Ollama request settings. Actual storage/Job/smoke checks
are recorded separately under `results/`; unit-test fake labels are never uploaded.

Stop only monitoring with Ctrl-C; Jobs remain intact. To suspend labelling while
preserving checkpoints:

```sh
kubectl -n pipeline patch job teacher-0 --type=merge -p '{"spec":{"suspend":true}}'
kubectl -n pipeline patch job teacher-1 --type=merge -p '{"spec":{"suspend":true}}'
```

Resume by setting `suspend` to `false`. To shut down the cluster while preserving
its Docker node and data, use `k3d cluster stop command-parser`; restart with
`k3d cluster start command-parser`. Stopping native Ollama interrupts workers, so
suspend or finish Jobs first. After exporting everything, permanent teardown is:

```sh
make down
```

Do not tag this partial assignment `final`: Tasks 2–7 remain outside this work.
No remote push or GitHub publication is performed.

Implementation references: [k3d configuration](https://k3d.io/stable/usage/configfile/),
[SeaweedFS S3 configuration](https://github.com/seaweedfs/seaweedfs/wiki/S3-Configuration),
[Ollama generation API](https://docs.ollama.com/api/generate).

Additional executed verification: `results/tests-live.log` records **39 passing tests**, including the opt-in live S3 test (put/read/overwrite/metadata/delete).
To repeat it against the local running cluster:

```sh
TASK1_S3_TEST=1 .venv312/bin/python -m pytest -q
.venv312/bin/python scripts/check_repository.py
```

`results/resume-verification.json` and `resume-*.log` show a real Kubernetes replay
of the five smoke checkpoints: five resumed IDs and zero new teacher labels.
`check_repository.py` checks supplied-file hashes and scans artifacts for the
actual generated S3 credentials and Kubernetes private key; its scope is narrower
than a general secret scanner. Neither it nor the unit tests claims completion
of the later Task 6 CI requirements.

After export, complete ID accounting and checksum regeneration can also be
verified **offline**, without Docker, Ollama or S3 credentials:

```sh
.venv312/bin/python scripts/verify_results.py
```

This reads the original pool and the two saved raw shards, independently checks
partition membership and source texts, reruns cleaning, compares the exact bytes,
checksum and counts, and writes `results/full/offline-verification.json`.


## Recovery observed during the full run

SeaweedFS exceeded its initial 768 MiB limit and restarted. Its replacement uses
2 GiB maximum memory, a 1 GiB Go memory target (`GOMEMLIMIT`) and `GOGC=50`.
Volume slots were increased to 16. One interrupted volume tail was reported as
read-only by SeaweedFS. After labelling, every S3 object was exported and restored
with verified hashes into `/data/recovered` on the same persistent volume. The
original files are retained outside that subdirectory; the active storage no
longer uses the interrupted volume. All 2,349 existing per-ID checkpoints downloaded and verified without
failure before resuming (`results/recovery/checkpoint-verification.json`); backups
of those exact records are retained there. Aggregate shard objects now publish
at the first record, every 25 records, and the final record, reducing rewrite
churn. Each individual reply is still immediately checkpointed and verified.

Ollama also returned `prediction aborted, token repeat limit reached` on C2273.
A cold model reload did not resolve it. Streaming transport exposed the teacher's
actual malformed output and repeated newlines, which non-streaming mode discards
on HTTP 500. The worker now concatenates response chunks without alteration. An
explicit repetition abort after emitted tokens is logged as `teacher_aborted`,
and those genuine partial tokens are stored for normal cleaning rejection.
An empty error or interrupted transport without an explicit repetition abort is
retried. Prompt, model, temperature, seed, context and token limits did not change.
No fallback label, JSON repair, or fabricated error label is inserted. Raw
protocol diagnostics are saved under `results/ollama-C2273-*.json`.

Recovery resumes the original Jobs and their durable checkpoints; it does not
launch a second full dataset run. A separate fresh five-command streaming smoke
run is retained under `results/smoke-stream/` and
`s3://datasets/teacher/smoke-stream/`. Old failure logs and the interrupted
monitor log are preserved. Concurrency measurement includes original and retried
Pods, comparing execution intervals only between different shard indices.


Storage migration evidence is in `results/storage-export-manifest.json`,
`storage-migration.json`, and `storage-restore.log`. The ignored backup is under
`.local/s3-backup/`. `scripts/storage_snapshot.py export` and `restore` implement
that byte-preserving recovery; do not run a restore while workers are writing.
The fresh storage subdirectory is created by an init container, so fresh setup
uses the same final manifest. Full ID coverage, checksum regeneration and live
S3 tests are repeated after migration.
