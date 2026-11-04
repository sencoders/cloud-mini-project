# Task 3 measured results

The FastAPI service uses the unchanged Task 2 CPU inference runtime. Each startup
fetches the model/tokenizer from authenticated SeaweedFS and verifies every file
against model.sha256. Credentials come explicitly from Secret-derived environment
variables; no host credential fallback or embedded model is used.

- Docker CLI image size: **1.33GB**, below 2 GB. Docker's
  containerd content-size field separately reports 274895002 bytes.
- Official CPU wheel: torch 2.8.0+cpu, CUDA absent; all dependencies pinned.
- Limits: **1 CPU, 1 GiB RAM, 1 GiB memory+swap** (no extra swap allowance).
- **50 / 50 sequential requests returned HTTP 200**, valid exact four-key bodies,
  correct version/actual-hostname headers, and frames identical to the saved Task 2
  V1 predictions for the same commands.
- Actual cgroup-v2 memory peak: **845602816 bytes
  (806.43 MiB)**. OOMKilled=false; oom/oom_kill events=0.
- /healthz stayed 200 while /readyz was 503 during download/loading, then /readyz
  became 200 after model and tokenizer loading completed.
- FAULT_INJECT=1 performed real generation, replaced its text before validation,
  and returned HTTP 500 with exactly {"error":"invalid_model_output"}.

The first service run also passed its 50 requests and fault check, but the harness
failed during post-processing due to a missing Python import path. Its genuine
logs remain in initial-harness-run/. The corrected, complete repeat is under
`results/task3/docker-runs/20261104T134242015031Z`. No resource limit was increased and no model weights,
training data, teacher labels or provided scripts were changed. Runtime model
files are downloaded into container temporary storage, outside image layers.
