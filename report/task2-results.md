# Task 2 measured results

Historical Task 2 milestone: local checks and publication state below describe that stage. Current remote verification is recorded in results/publication/outcome.json and docs/publication-audit.md.

CPU-only full fine-tuning of exactly EleutherAI/pythia-70m; no adapters or substitute student.
The execution Mac reports Apple M5. Python 3.12.16; exact libraries and the source revision are in training/config.yaml.

## Training and artifacts

| Run | Records | Epochs | Whole command (s) | Training loop (s) | Steps/s | Peak RSS (GiB) |
|---|---:|---:|---:|---:|---:|---:|
| smoke | 50 | 3 | 8.07 | 5.267 | 7.404 | 2.288 |
| v1 | 1500 | 3 | 147.99 | 145.259 | 7.745 | 2.017 |
| v2 | 1500 | 1 | 50.98 | 48.472 | 7.736 | 1.818 |

V1 uses three epochs from the base checkpoint. V2 uses one additional epoch from V1 with a fresh AdamW optimizer (four cumulative epochs). Both use the same first 1,500 cleaned records, C0001 through C2004, in verified ID order before deterministic epoch shuffling.
The exact teacher_raw strings are targets; command and padding loss are masked, real EOS is supervised, and no sequence was truncated.
The dataset SHA-256 is `1865c9ddc2a723247e96336c0ef966cd3b669aa904ae03d29f77ef4fe92b03e5`. No provided validation text overlaps the selected training commands; no validation labels are used for training.
Two independent 50-example runs produced identical model weights and epoch losses (results/task2/smoke-reproducibility.json). The initial smoke rate predicted about 150.15 seconds of V1 training and 50.05 seconds of V2 training; these were estimates, separately recorded before full runs.

All model/tokenizer/config/version files were uploaded to `s3://models/v1/` and `s3://models/v2/`, read back byte for byte, downloaded into separate local directories, and loaded on CPU. The per-file manifests are `models/v1/model.sha256` and `models/v2/model.sha256` in the bucket and repository. Weight-file hashes differ between V1 and V2.

## Validation: exact raw-output score.py metrics (%)

| Model | JSON validity | Intent | Date | Time | Place | Full frame |
|---|---:|---:|---:|---:|---:|---:|
| teacher | 83.00 | 74.00 | 64.00 | 64.00 | 76.00 | 44.00 |
| untrained | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| student_v1 | 100.00 | 80.00 | 66.00 | 70.00 | 77.00 | 26.00 |

Every report covers all 100 IDs with zero missing predictions. The teacher used the exact Task 1 prompt hash, phi3.5 model digest, temperature 0, seed 42, JSON mode, 2,048 context tokens and a 256-token output bound.
Student and untrained generation are greedy CPU decoding, bounded at 128 new tokens with EOS handling. Primary metrics score untouched completion text; no extraction, repair, fallback frame or gold label is substituted. Lossless extraction results are saved separately and are not the table above.
The untrained model produced no valid command frames. Distillation improved JSON syntax to 100% on this validation set and intent accuracy to 80%, but student full-frame accuracy is 26% versus the teacher's 44%. Slot correctness remains limited; high null-slot accuracy and valid formatting are not evidence of complete semantic understanding. Validation results do not establish hidden-test performance or a deployed-service SLO.

## Reproducibility and publication status

65 tests passed, including live S3 operations, dataset selection/checksum guards, completion/padding/EOS masks, generation bounds, JSON validation, artifact tampering checks and rejection of smoke artifacts for publishing.
The original Task 1 dataset remains unchanged, and SeaweedFS and its existing buckets were neither restarted nor deleted during Task 2.
Verified local Release archives exist under `.local/releases/`; the archives contain the same files described by the S3 manifests. Each archive has a separate SHA-256 sidecar. No GitHub Release has been published. No Git remote is configured, and no Git commits have been pushed. The manual packaging/publication workflow and prerequisites are in docs/releases.md. Publication requires a GitHub repository, an existing remote tag, runner/network access to SeaweedFS, and explicit publication authorization.
The sequence-level versus logit-based explanation, suitability assessment and limitations are in docs/distillation.md. This Task 2 milestone predates deployment; later task reports document subsequent work.
