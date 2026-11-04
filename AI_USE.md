# AI use

OpenAI Codex assisted with reading the assignment, implementing Task 1 infrastructure,
S3 operations, worker, cleaner, tests, orchestration, and documentation. Verification
uses automated tests, real Docker/Kubernetes execution, an Ollama five-command smoke
run, S3 byte-for-byte read-back, complete source-ID accounting, and SHA-256 checks.
Measured evidence is under results/. Incomplete work is identified there and in README.md.

Teacher labels are generated only by the required native Ollama phi3.5:latest model,
with temperature 0 and seed 42. Codex does not create or manually repair teacher labels.
At Task 1 completion no student model had been trained; Task 2 work is recorded below. Supplied validation labels are not used for labelling
or training. No paid inference API is used by this pipeline.


For Task 2, Codex assisted with the CPU-only PyTorch/Transformers pipeline,
completion/padding masking, source/data checksums, versioning, reusable inference,
evaluation, packaging and documentation. Verification included 65 passing tests,
two independent smoke runs with identical weight hashes and losses, complete
1,500-record V1/V2 CPU training, S3 read-back and separate checkpoint reloads,
and actual score.py evaluation of all 100 validation records for three models.
The teacher, untrained and student raw completions are retained. No manual labels,
output repair, gold-label fallback or fabricated measurement was used. Teacher
validation called the same Task 1 model/prompt/settings. No GitHub Release was
published and no Git commits were pushed during this work.


Task 3: Codex assisted with the FastAPI service, Secret-only S3 startup,
checksum verification, Docker build, tests and measurement harness. Verification
uses the real trained V1 model, 50 sequential requests at the assignment limits,
actual cgroup peaks/OOM counters, response comparisons with stored Task 2 outputs,
and the explicit fault-injection test. Initial harness failure evidence is retained.
No model weights or credentials are committed, and no labels are altered.


Task 4: Codex assisted with app manifests, Secret wiring, probes, Ingress,
rollout/recovery/HPA orchestration, resumption guards, diagnosis and reporting.
Checks used real Kubernetes state, unchanged instructor Locust runs, S3 download
logs and Pod timestamps. Completed cold starts and the baseline were preserved
through resumption. Nonzero Locust exits and all HTTP 500s are retained; the
rolling failure threshold is explicitly unmet. Inference/training code, data and trained artifacts from Tasks 1–3 were preserved.
Those expensive pipelines were not repeated; combined unit tests were rerun. A single local V2 inference was used only
to diagnose the failing probe, not to train, relabel or replace a served output.

Tasks 5–7: Codex assisted with VLSM calculations, stateless first-match NACL rules,
network boundary tests, performance/cost/SLO calculations, Release verification,
bootstrap/teardown guards, GitHub Actions and the report. Checks used the unchanged
instructor packet simulator (6/6), new focused tests and the full unit suite,
original Task 4 Locust/resource/cold-start measurements, Decimal cost calculations,
actual local Release archive/member hashes and the supplied scorer on preserved
raw predictions. Ruff and Gitleaks were run locally. Gitleaks initially found a
public Docker GPG fingerprint; the original diagnostic and narrowly scoped public
fingerprint exception are documented. Existing measurements and failed thresholds
remain visible. No remote workflow, failed-run URL or Release publication was
invented. No teacher labels, training artifacts or instructor scripts were changed.
The generated report is typeset project evidence, not the mandatory handwritten
personal reflection, which the student must supply themselves.
