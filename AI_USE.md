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
