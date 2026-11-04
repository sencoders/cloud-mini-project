# AI use

OpenAI Codex assisted with reading the assignment, implementing Task 1 infrastructure,
S3 operations, worker, cleaner, tests, orchestration, and documentation. Verification
uses automated tests, real Docker/Kubernetes execution, an Ollama five-command smoke
run, S3 byte-for-byte read-back, complete source-ID accounting, and SHA-256 checks.
Measured evidence is under results/. Incomplete work is identified there and in README.md.

Teacher labels are generated only by the required native Ollama phi3.5:latest model,
with temperature 0 and seed 42. Codex does not create or manually repair teacher labels.
No student model has been trained. Supplied validation labels are not used for labelling
or training. No paid inference API is used by this pipeline.
