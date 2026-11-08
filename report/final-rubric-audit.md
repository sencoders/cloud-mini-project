# Final examiner-style audit — Shreeja Chaudhary, 230101089

This audit uses ASSIGNMENT.pdf Sections 6–8 and every marking table. PASS means the recorded local/remote evidence supports that criterion, not an official awarded grade. UNVERIFIED criteria receive no evidence-supported credit. Hidden tests are unavailable. This scorecard is the pre-closeout assessment. The real handwritten reflection has now been received and visually verified; final archive/tag checks follow the procedure in docs/final-submission.md.

## A. Training authenticity verdict

**PASS: the available evidence strongly supports genuine CPU fine-tuning of exactly EleutherAI/pythia-70m. No retraining is indicated.** Speed alone is not a validity test. Friends' runtimes cannot be compared without their model, sequences, examples, epochs, batching and hardware.

- Official source revision: `a39f36b100fe8a5377810d56c3f4789b9c53ac42`. The locally cached base SHA-256 equals its recorded official Hugging Face LFS SHA. Architecture: GPT-NeoX, six layers, hidden size 512, eight attention heads, vocabulary 50,304; **70,426,624 trainable parameters**. Both saved checkpoints reload as CPU float32, with the same parameter count.
- The base file is FP16 and contains 18 historical attention-mask/rotary buffer entries absent from the modern saved state. The audit compares all **76 shared trainable tensors after float32 conversion**, not just file sizes or hashes. These buffer-format differences are not missing trained parameters.
- Verified cleaned pool: **2,225 records**, SHA-256 `1865c9ddc2a723247e96336c0ef966cd3b669aa904ae03d29f77ef4fe92b03e5`. Selection is exactly the first **1,500**, ID order C0001…C2004. Selected bytes SHA `71ea7545a081a521335121b75da6d10d220591ad7b1593f4ec72faa26d8b2bc2`; teacher-target-string SHA `926f678e62e4ae750608c40a1b1bfb63b57c3c0ced3bc56db36d388972a3d27c`. These independently match the saved data provenance.
- Training targets are original `teacher_raw`, never reconstructed gold labels. The training path reads the verified cleaned object, not validation; selected training text and IDs do not overlap validation. Minibatch shuffling after ordered selection is deterministic and permitted: the assignment fixes which records, not their epoch iteration order.
- Recipe: batch **4**, accumulation **1** (optimizer step every batch), AdamW, learning rate **0.0003**, seed **42**, max sequence length **256**, clip norm **1.0**, weight decay **0.01**, four CPU threads, one interop thread; V1 three epochs, V2 one additional epoch from V1 with a new AdamW optimizer.
- Actual source execution order is `model.train()` → CPU forward loss → finite-loss check → `loss.backward()` → gradient clipping → `optimizer.step()` → step record. The source moves every model/batch tensor explicitly to CPU and enables deterministic algorithms. All replayed checkpoint parameters are CPU float32 and require gradients.
- Each epoch has **375 optimizer steps**, **54,313 unpadded input tokens including EOS** (recomputed) and **34,511 supervised tokens including EOS** (recorded and independently reproduced). Input lengths are **28–66**, mean **36.208667**. No sequence was truncated; lengths above 256 raise an error. No prompt/completion boundary-straddling token was found.
- Prompt labels and padding labels are -100. Real EOS remains supervised with attention 1 even though padding uses the same token ID 0. Causal-LM shifting predicts the next token; targets are not copied from the current input position as an identity loss. Every saved step target-token count matches reconstruction of the original seeded DataLoader, and weighted epoch losses reproduce exactly.

| Run | Records/epoch | Epochs | Steps/epoch | Total updates | Supervised tokens | Recomputed unpadded input tokens | Training loop | Whole shell command |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V1 | 1,500 | 3 | 375 | 1,125 | 103,533 | 162,939 | 145.259 s | 147.99 s |
| V2 | 1,500 | 1 | 375 | 375 | 34,511 | 54,313 | 48.472 s | 50.98 s |
| Timed smoke | 50 | 3 | 13 | 39 | 3,414 | first-50 subset | 5.267 s | 8.07 s |

Total full training: **1,500 updates and 138,044 supervised tokens**, about 199 seconds of shell runtime. Dynamic batch padding, rather than padding every example to 256, explains much of the small workload. Reconstructed padded-input totals are 61,936 / 61,864 / 61,932 for V1 epochs and 61,936 for V2; these are audit reconstruction, not originally logged input telemetry.

| Epoch | Token-weighted training loss | Steps | Supervised tokens |
|---|---:|---:|---:|
| V1/1 | 1.546307489 | 375 | 34,511 |
| V1/2 | 0.681336552 | 375 | 34,511 |
| V1/3 | 0.364350027 | 375 | 34,511 |
| V2/1 | 0.319773666 | 375 | 34,511 |

V1 shell timing records **339.25 user CPU seconds + 11.65 system seconds over 147.99 wall seconds**; V2 records 114.51 + 4.50 over 50.98. This is consistent with multithreaded CPU work. Observed step rates are 7.745 and 7.736 updates/s. Low completion loss partly reflects repeated JSON syntax and null values; it does not imply semantic correctness or hidden-test success.

| Numeric comparison | Changed parameters after common float32 cast | Max absolute difference | L2 difference |
|---|---:|---:|---:|
| Base → V1 | 70,426,401 / 70,426,624 | 0.223670959 | 43.926052319 |
| V1 → V2 | 70,426,233 / 70,426,624 | 0.074371338 | 21.847713588 |

All 76 trainable tensors change in both comparisons. A separate check rejects the hypothesis that only uniform AdamW weight decay or dtype conversion caused the differences: maximum residuals versus pure decay are **0.179932** (base→V1) and **0.054459** (V1→V2). Checkpoint manifests match the committed/public manifests; no checkpoint was modified by this audit.
Fresh CPU reloads reproduced V1 raw outputs for V001, V066 and V100 exactly, including V066's invalid `datetime_set`; V2 exactly reproduced its saved malformed duplicate-key diagnostic. Those failures are retained. Existing all-100 raw V1 replay in actual GitHub CI also matched the original Task 2 output byte-for-byte.
Historical gradient tensors and optimizer-state checkpoints were not saved, so this is an evidence-based audit of source ordering, step records, exact token/loss reconstruction, changed tensors and replay—not independent hardware attestation of every historical operation. No invented gradient statistics are claimed.
`make train SUBSET=50` selects the first 50 and uses isolated timestamped checkpoints; historical smoke completed twice with identical weights/losses. `make train` selects 1,500 and deliberately refuses overwriting an existing full checkpoint. On the current machine a second full run should fail that protection, not destroy evidence. Clean-machine execution is still separately unverified. A real portability bug was reproduced: the old exact-string guard rejected official `2.8.0+cpu`. The narrow fix accepts only the configured upstream version and its `+cpu` build, still rejects explicit CUDA suffixes/different versions, and records `torch_runtime_version` on future training. No training parameters, saved models or old metadata were changed.
Quantitative evidence: `results/final-audit/training-authenticity.json`, `optimizer-effect-check.json`, `checkpoint-replay.json`, `cpu-wheel-guard-before.json`, `cpu-wheel-guard-after.json`; original `training/loss.csv`, `results/task2/v{1,2}/steps.jsonl`, summaries/data/tokenization/manifests, and timed command logs.

## B. Criterion-by-criterion 100-mark scorecard

**Provisional evidence-supported total: 84/100. Conditional working range: 84–96/100, assuming existing evidence is accepted and a valid final submission is completed. This is not a guaranteed floor or awarded mark.** Four points are currently unavailable under this audit (rolling threshold 2; blocked fresh bootstrap 2). Twelve further points depend on hidden or assessor-machine tests; they are not awarded here. The Task 7 performance row is bundled for two marks, so no invented one-mark split is assumed. Its local error threshold fails, although assessor-machine behavior is unverified. If the examiner treats that bundle as a local all-or-nothing failure, the conditional ceiling is lower.

| Task | Max | Supported by current evidence | Conditional ceiling |
|---|---:|---:|---:|
| 1 | 12 | 12 | 12 |
| 2 | 20 | 14 | 20 |
| 3 | 14 | 14 | 14 |
| 4 | 22 | 20 | 20 |
| 5 | 10 | 6 | 10 |
| 6 | 10 | 8 | 8 |
| 7 | 12 | 10 | 12 |
| **Total** | **100** | **84** | **96** |

At-risk marks below mean maximum minus supported marks, including unverified points; they are not all definite deductions. Only the verified commit ultimately tagged final is the assessed source snapshot. Reflection/submission requirements have no separate numeric allocation in the seven-task tables, so no invented reflection mark is added or subtracted.

| Task / criterion | Max | Status | Supported–conditional | At risk | Evidence and measured result | Fastest legitimate fix |
|---|---:|---|---:|---:|---|---|
| 1: Cluster config and storage in data | 2 | PASS | 2–2 | 0 | cluster/k3d.yaml; results/cluster-create.log; results/storage.json: Recorded k3d/SeaweedFS deployment | Preserve existing verified evidence |
| 1: Buckets, source pool, prompt | 2 | PASS | 2–2 | 0 | results/storage.json; prompts/teacher_prompt.txt: datasets/models and source-pool read-back verified | Preserve existing verified evidence |
| 1: Two concurrent sharded workers | 2 | PASS | 2–2 | 0 | results/full/concurrency.json; report/task1-results.md: Distinct shards; at least 2,173 s overlap | Preserve existing verified evidence |
| 1: Every source ID exactly once | 2 | PASS | 2–2 | 0 | results/full/shard-0.jsonl; results/full/shard-1.jsonl: 3,000 unique IDs, no gaps/repeats | Preserve existing verified evidence |
| 1: Cleaner reproduces checksum | 2 | PASS | 2–2 | 0 | results/full/counts.json; results/final-audit/task1-recheck.json: 2,225 kept; SHA-256 1865c9dd... | Preserve existing verified evidence |
| 1: Complete rejection/accounting table | 2 | PASS | 2–2 | 0 | results/full/counts.json; report/report.pdf: 3000=2+2+526+202+43+2225 | Preserve existing verified evidence |
| 2: Six configuration items | 2 | PASS | 2–2 | 0 | training/config.yaml: Seed/lr/batch/epochs/max length/exact upstream versions recorded | CPU-build compatibility fix implemented; parameters unchanged |
| 2: SUBSET=50 completes on assessor machine | 2 | UNVERIFIED | 0–2 | 2 | results/task2/smoke-timed-command.log; results/final-audit/cpu-wheel-guard-before.json; compatibility-tests.log: Historical real 8.07 s smoke; official +cpu build guard bug fixed; assessor run unavailable | Use official CPU wheel; run make train SUBSET=50 only when fresh-machine verification is required |
| 2: Per-epoch loss and fixed seed | 2 | PASS | 2–2 | 0 | training/loss.csv; results/final-audit/training-authenticity.json: V1 losses 1.546307→0.681337→0.364350; V2 0.319774; seed 42 | Preserve logs; no retraining indicated |
| 2: Both models/tokenizers in object storage | 2 | PASS | 2–2 | 0 | results/task2/v1/s3-upload.json; results/task2/v2/s3-upload.json; results/task2/s3-checkpoint-reload.json; results/final-audit/live-storage-manifests.json: 18 S3 objects; both 70,426,624-parameter CPU checkpoints read-back verified | V2 Release is separate from this S3 criterion |
| 2: Release asset matches model manifest | 2 | PASS | 2–2 | 0 | results/publication/v1-downloaded-verification.json; models/v1/model.sha256: Published/downloaded V1 archive and every member match committed manifest | V1 is the explicitly required Release; V2 upload is not a direct extra deduction here |
| 2: Three raw evaluations and matching table | 2 | PASS | 2–2 | 0 | results/{teacher,untrained,student_v1}_validation.json; results/task2/evaluation/; report/report.pdf: All 100 IDs; teacher 83/74/64/64/76/44, student 100/80/66/70/77/26 | Preserve raw output and supplied scorer |
| 2: Hidden service JSON validity >=95% | 2 | UNVERIFIED | 0–2 | 2 | results/task2/evaluation/student_v1_provenance.json; results/final-audit/checkpoint-replay.json: Raw validation shape 100%; strict intent/schema 99/100; hidden 300 not provided | Test general schema-constrained generation separately; never accept invalid output as success |
| 2: Hidden full-frame target | 2 | UNVERIFIED | 0–2 | 2 | results/teacher_validation.json; results/student_v1_validation.json: Teacher 44% implies 22% target; student validation 26%, hidden unknown; >0% alone yields partial credit | Independent evaluation on genuinely unseen labels; no hidden/gold fallback |
| 2: Sequence-level definition | 1 | PASS | 1–1 | 0 | docs/distillation.md; report/report.pdf: Exact teacher-generated text is supervised target | Keep explanation within one page |
| 2: Logit-based definition | 1 | PASS | 1–1 | 0 | docs/distillation.md; report/report.pdf: Soft token distributions / KL comparison | Keep explanation within one page |
| 2: Why logits unavailable here | 1 | PASS | 1–1 | 0 | docs/distillation.md; report/report.pdf: Required Ollama-generated artifacts provide no aligned full teacher logits | Keep explanation within one page |
| 2: Real limitation | 1 | PASS | 1–1 | 0 | docs/distillation.md; report/report.pdf: Teacher errors and limited semantic full-frame accuracy | Keep explanation within one page |
| 3: Endpoints and two headers | 2 | PASS | 2–2 | 0 | service/app.py; tests/test_service.py; results/task3/docker-results.json: Health/readiness/parse and actual hostname/version headers verified | Preserve real Docker evidence |
| 3: Exact fault-injection 500 | 2 | PASS | 2–2 | 0 | results/task3/docker-results.json; tests/test_service.py: FAULT_INJECT=1: exact invalid_model_output error | Preserve real Docker evidence |
| 3: Startup download, no embedded weights | 2 | PASS | 2–2 | 0 | service/Dockerfile; .dockerignore; results/task3/*/image-audit.json: Authenticated S3 download and artifact checks; no weights in image | Preserve real Docker evidence |
| 3: Four environment vars and Secret credentials | 2 | PASS | 2–2 | 0 | service/app.py; service/storage.py; cluster/app.yaml: All required settings consumed; explicit Secret-derived credentials | Preserve real Docker evidence |
| 3: Every dependency pinned | 1 | PASS | 1–1 | 0 | service/Dockerfile; service/requirements.txt: Base image pinned by SHA-256; CPU PyTorch and Python dependencies pinned | Preserve real Docker evidence |
| 3: Image <=2 GB | 1 | PASS | 1–1 | 0 | results/task3/docker-results.json: Docker disk size 1.33 GB | Preserve real Docker evidence |
| 3: 50 sequential requests at 1 CPU/1 GiB, no OOM | 2 | PASS | 2–2 | 0 | results/task3/docker-results.json: 50/50 HTTP 200; cgroup memory limit 1073741824; zero OOM events | Preserve real Docker evidence |
| 3: Measured peak memory evidence | 1 | PASS | 1–1 | 0 | results/task3/docker-results.json: 845602816 bytes = 806.43 MiB | Preserve real Docker evidence |
| 3: One-command fresh-clone image build | 1 | PASS | 1–1 | 0 | results/final-audit/fresh-clone-image.json; fresh-clone-image-commands.log: Actual fresh local Git clone at 2381683; one Docker build succeeded in 0.695 s using cached layers; CPU/no-weights probe passed; original tag untouched | Fresh clone uses existing Docker cache; not a claim of a cache-free build on assessor hardware |
| 4: App namespace, Deployment, Service, Ingress | 4 | PASS | 4–4 | 0 | cluster/app.yaml; results/task4/initial/; ingress-probe.json: Two replicas initially deployed; /parse through Traefik | Preserve existing successful measurements |
| 4: Requests and limits set | 2 | PASS | 2–2 | 0 | cluster/app.yaml; results/task4/load-balancing/before/resources.json: Per app Pod: 1 CPU/1 GiB limit; requests configured | Preserve existing successful measurements |
| 4: No ready endpoints during loading | 2 | PASS | 2–2 | 0 | results/task4/cold-starts/; initial-readiness.json: Zero ready endpoints during measured S3/model loads | Preserve existing successful measurements |
| 4: HPA specified settings | 2 | PASS | 2–2 | 0 | cluster/hpa.yaml; results/task4/summary.json: min=1 max=2 CPU target 70% | Preserve existing successful measurements |
| 4: Actual HPA 1→2→1 | 2 | PASS | 2–2 | 0 | results/task4/autoscaling/; autoscaling-load/: Recorded idle/load/idle scaling | Preserve existing successful measurements |
| 4: Rollback restores v1 header | 2 | PASS | 2–2 | 0 | results/task4/rolling/; version-verification/: Rollout V2 then rollout undo and V1 response headers | Preserve existing successful measurements |
| 4: Replica count restored | 1 | PASS | 1–1 | 0 | results/task4/recovery/: Two Ready replicas restored in 6.862672 s | Preserve existing successful measurements |
| 4: Recovery failures <=2% | 1 | PASS | 1–1 | 0 | results/task4/recovery/; summary.json: 3/320=0.9375%, passes | Preserve existing successful measurements |
| 4: Three cold starts and median/download logs | 2 | PASS | 2–2 | 0 | results/task4/cold-starts/summary.json: Run medians 5,5,4 s; overall 5 s; six Pod observations | Preserve existing successful measurements |
| 4: Each of exactly two replicas >=30% | 2 | PASS | 2–2 | 0 | results/loadtest_headers.json; results/task4/load-balancing/: 188/186 successful responses: 50.27%/49.73% | Preserve existing successful measurements |
| 4: Rolling failure rate <=0.5% | 2 | FAIL | 0–0 | 2 | results/task4/rolling/; results/task4/summary.json: 24/308=7.792%, all recorded failures retained | Validate genuinely better/constrained V2 generation; rerun required Docker/evaluation/rollout checks; do not repair labels or weaken schema |
| 5: app five subnet values | 1 | PASS | 1–1 | 0 | network/subnets.md: 10.20.0.0/22; 1022 usable; ranges/broadcast/calculations correct | None |
| 5: public five subnet values | 1 | PASS | 1–1 | 0 | network/subnets.md: 10.20.4.0/24; 254 usable; ranges/broadcast/calculations correct | None |
| 5: data five subnet values | 1 | PASS | 1–1 | 0 | network/subnets.md: 10.20.5.0/25; 126 usable; ranges/broadcast/calculations correct | None |
| 5: management five subnet values | 1 | PASS | 1–1 | 0 | network/subnets.md: 10.20.5.128/27; 30 usable; ranges/broadcast/calculations correct | None |
| 5: Twenty hidden NACL packets | 4 | UNVERIFIED | 0–4 | 4 | network/nacl.json; results/task5/; tests/test_network.py: 6/6 provided packets; 24 packet/boundary cases plus VLSM test; hidden packets unavailable | Keep exact first-match stateless rules; add independent properties if needed; never claim hidden results |
| 5: Stateless replies explanation | 1 | PASS | 1–1 | 0 | network/subnets.md: Explicit separate inbound app and outbound client ephemeral replies | None |
| 5: Abusive CIDR rule-order explanation | 1 | PASS | 1–1 | 0 | network/subnets.md; network/nacl.json: Rule 100 deny precedes web allows | None |
| 6: Lint stage | 1 | PASS | 1–1 | 0 | .github/workflows/ci.yml; results/final-audit/ci-runs.json: Real GitHub lint passed | Preserve verified remote evidence |
| 6: Unit stage with >=3 tests | 1 | PASS | 1–1 | 0 | tests/; results/submission/full-tests.log; GitHub CI: 145 prior local tests, plus new audit tests; actual CI unit pass | Preserve verified remote evidence |
| 6: Evaluation downloads actual Release | 2 | PASS | 2–2 | 0 | results/publication/normal-ci-full.log; .github/workflows/ci.yml: Actual V1 asset download, SHA checks and all-100 CPU evaluation passed | Preserve verified remote evidence |
| 6: Genuine failed-quality-gate URL | 2 | PASS | 2–2 | 0 | report/report.pdf; results/publication/bad-model-ci-verification.json: 42030357782: evaluation passed; real untrained 0% fails unchanged 95% gate | Preserve verified remote evidence |
| 6: AI disclosure and zero secret scan | 1 | PASS | 1–1 | 0 | AI_USE.md; .gitleaks.toml; results/publication/*gitleaks*: Truthful Codex/Ollama disclosure; exact public-fingerprint exception; zero configured findings | Preserve verified remote evidence |
| 6: Fresh-clone make up in <=3 commands | 2 | FAIL | 0–0 | 2 | scripts/system.py; results/final-audit/fresh-bootstrap-v2-prerequisite.log: Fresh path requires missing V2 archive; actual exact asset fetch: no assets match the file pattern | Upload verified V2 on faster connection, then disposable full fresh-clone test; do not silently omit V2 |
| 6: make down deletes the cluster | 1 | PASS | 1–1 | 0 | results/final-audit/isolated-teardown.json: Real make down deleted separately created cs3081-teardown-audit; original cluster/storage UIDs preserved | Default working-cluster deletion deliberately not performed; same command path exercised with explicit test name |
| 7: All five measured quantities and Locust files | 2 | PASS | 2–2 | 0 | results/loadtest*.csv; results/task4/load-balancing/; report/task7-results.md: p50 1100 ms, p95 2000 ms, 3.331958 req/s, 4/378 failures, per-Pod resources, cold median 5 s | Preserve all raw CSV/console count differences |
| 7: Assessor error <=1% AND p95 <=5000ms | 2 | PARTIAL | 0–2 | 2 | results/task7/summary.json; results/task4/load-balancing/: Local p95 passes at 2000 ms, local failures 1.058% exceed 1%; assessor hardware/request mix unknown | General valid generation improvement then new controlled standard run; do not cherry-pick a lucky run |
| 7: Correct rate-card cost and all calculations | 3 | PASS | 3–3 | 0 | data/rate_card.json; results/task7/summary.json; report/task7-results.md: 2×(3.50+0.45)=7.90 INR/h; rps×3600=11995.048; cost=0.65860512 INR/1000 | Estimate explicitly excludes non-app costs, includes failed attempts |
| 7: SLO target and window | 1 | PASS | 1–1 | 0 | report/task7-results.md: 99% HTTP 200 over one complete standard two-minute run | None |
| 7: Request error-budget arithmetic | 1 | PASS | 1–1 | 0 | results/task7/summary.json: 378×1%=3.78; floor=3 whole failures; 4 consumed=133.33% of whole budget, not met | Keep fractional vs whole-request convention explicit |
| 7: Review: Data/storage | 0.5 | PASS | 0.5–0.5 | 0 | report/report.pdf; report/task7-results.md: 2225/3000 kept; limitation and improvement included | None |
| 7: Review: Model quality | 0.5 | PASS | 0.5–0.5 | 0 | report/report.pdf; report/task7-results.md: 80% intent, 26% full frame; limitation and improvement included | None |
| 7: Review: Latency/throughput | 0.5 | PASS | 0.5–0.5 | 0 | report/report.pdf; report/task7-results.md: p95 2000 ms; 3.332 req/s; limitation and improvement included | None |
| 7: Review: Resource use | 0.5 | PASS | 0.5–0.5 | 0 | report/report.pdf; report/task7-results.md: 998m CPU; 430 MiB sampled; limitation and improvement included | None |
| 7: Review: Reliability/recovery | 0.5 | PASS | 0.5–0.5 | 0 | report/report.pdf; report/task7-results.md: 6.863 s restore; rolling 7.792%; limitation and improvement included | None |
| 7: Review: Security/cost | 0.5 | PASS | 0.5–0.5 | 0 | report/report.pdf; report/task7-results.md: 0 known-key findings; cost labelled estimated; limitation and improvement included | None |

## C. Confirmed failures versus unverified criteria

**Confirmed:** rolling 24/308 failures = 7.792% >0.5%; baseline 4/378 = 1.058% >1%; the 99% SLO is not met. These are model-validation HTTP 500s, not excluded requests. Fresh bootstrap currently requests absent `pythia-70m-v2.tar.gz`; actual CLI check returns `no assets match the file pattern` before a new cluster could be started. V2 remains valid in SeaweedFS, so this is not a failure of the separate Task 2 two-S3-version criterion. The PDF explicitly requires V1 publication; missing V2 Release is not automatically an additional Task 2 Release deduction.
**Unverified:** hidden 300-command service validity/full-frame scores; hidden 20 NACL packet outcomes; assessor-machine smoke run; assessor-machine latency/error bundle; full fresh-clone deployment. Validation 26% full frame exceeds the teacher-derived 22% target only on the provided 100, not the hidden set. Raw scorer JSON 100% differs from strict runtime schema 99/100.
**Submission closeout:** actual handwritten `230101089.pdf` is now received and visually verified on all three pages, with correct name, roll number and GitHub link. Final archive/tag checks follow docs/final-submission.md. Temporary synthetic PDF unit fixtures are not reflections or submission files. Report is seven pages with real identity and clickable verified links; performance gaps remain disclosed.

## D. Prioritized improvements and executed work

| Priority | Issue / marks exposed | Time / likelihood | Risk | Action / result |
|---|---|---|---|---|
| 1 | Missing real scan, ZIP and final assessed tag; gates the submission | User-dependent; verification/packaging minutes after receipt | Low if genuine scan is supplied | Request the real three-page scan with name/roll/repo; do not fabricate it or tag prematurely |
| 2 | CPU-wheel startup guard, within smoke reproducibility 2 marks | Minutes; high confidence | Low | Fixed exact +cpu compatibility; seven numerical/compatibility/environment tests passed; historical checkpoints unchanged; no retraining |
| 3 | Previously unexecuted make down, 1 mark | Under a minute after setup; high confidence | Low with isolated name and memory limit | Real disposable cluster created in 15.852 s; make down deleted it in 0.850 s; working cluster names and SeaweedFS Pod UIDs preserved. First minimal-configuration k3d failure retained; standard-settings retry succeeded |
| 4 | Fresh bootstrap blocked by V2 Release, 2 marks | Connection-dependent; poor likelihood on measured uplink | Low model risk, high deadline risk | Current Release checked; no more retries after prior 27 KB/s / timeout evidence. Use faster connection, verify SHA and then test fresh deployment on disposable resources |
| 5 | Hidden validity/full-frame, 4 marks; rolling 2; performance bundle 2 | Hours, uncertain improvement | Moderate/high | Proper schema-constrained token generation may help without gold fallback, but would require shared-runtime evaluation, CPU/memory Docker tests and new rollout/baseline evidence. Not rushed into the validated runtime |
| 6 | Hidden NACL 4; independent hardware variation | Build minutes/network-dependent; hidden cases inaccessible | Low for isolated build | Fresh-clone one-command image build now passed in 0.695 s with cached layers and a separate image tag; hidden NACL outcomes remain inaccessible |

No model training, teacher generation, schema relaxation, frame repair, threshold weakening, relabelling of failed requests, or lucky-run selection was performed. The oldest successful cold-start/load/HPA experiments were preserved. New work is a read-only authenticity audit, version-guard fix, isolated teardown verification, regression tests and truthful documentation.

## E. GitHub, model Release and security

- Repository: https://github.com/sencoders/cloud-mini-project (private). Ordinary source pushes are allowed; no `final` tag is authorized until the real scan and ZIP are verified.
- Audit-code CI passed all five jobs (including the real installed CPU-build environment regression): https://github.com/sencoders/cloud-mini-project/actions/runs/42078320293 at 69d569a.
- Verified pre-audit source CI: https://github.com/sencoders/cloud-mini-project/actions/runs/42048768489 (c320e3a, all jobs passed).
- Normal Release-backed evaluation/gate proof: https://github.com/sencoders/cloud-mini-project/actions/runs/42034879848 (all jobs passed).
- Genuine deliberately failed gate: https://github.com/sencoders/cloud-mini-project/actions/runs/42030357782 (real untrained model, all 100 evaluated, 0% validity; evaluation and secret scan passed, only quality gate failed).
- Release: https://github.com/sencoders/cloud-mini-project/releases/tag/models-v1-v2. V1 is published/download/member/version verified. V2 archive is absent; its checksum sidecar alone is not a model upload. V2 S3 and local model manifests remain valid.
- History/source secret scans retain all default Gitleaks rules with one reviewed exact public Docker GPG fingerprint exception. No real secret, token, kubeconfig or model weight is committed. Full history and current-source scans are refreshed at closeout; AI_USE.md remains truthful.
- The report remains within eight pages; this detailed Markdown audit is supplementary and does not pretend to be part of the seven-page main PDF.

## F. Final submission readiness and exact actions

1. User supplies the actual handwritten **230101089.pdf** (three pages, legible, Shreeja Chaudhary, roll 230101089, actual repository URL). This requirement is now fulfilled by the real scan received at project root.
2. Receive/copy the real scan byte-for-byte to ignored `.local/submission-input/230101089.pdf`; visually review handwriting/content and page count. Do not generate or substitute a scan.
3. Resolve V2 transfer/fresh bootstrap on a faster connection where practical; retain every old failure. Private repository/Release access must be available to the assessor.
4. Commit/push only checked source/report/evidence. With a clean source snapshot and reviewed actual scan: `make submission-plan REVIEWED=1`, then `make submission-zip REVIEWED=1`.
5. Verify `unzip -t submission/230101089.zip` and `(cd submission && shasum -a 256 -c 230101089.zip.sha256)`, and check the manifest commit matches HEAD. ZIP includes source/report/results plus actual scan and manifest; excludes Git internals, private state, environments, caches and weights.
6. Only after complete file/ZIP/Release review and successful CI for the intended final source commit, create/push `final` at that exact manifest commit. No tag is created in this audit. Submit the correctly named PDF/ZIP through the required portal before the actual deadline.

The final ZIP is built after committing this source snapshot; its exact hash, size, manifest and remote final-tag verification are retained in ignored submission/. No commits follow final tagging. The final response records the actual completion status.
