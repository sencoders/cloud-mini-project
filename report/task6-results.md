# Task 6: local reproducibility and CI/CD

Historical Task 6 milestone: local checks and publication state below describe that stage. Current remote verification is recorded in results/publication/outcome.json and docs/publication-audit.md.
## Verified remote execution

The source is private at https://github.com/sencoders/cloud-mini-project. V1 is
published and independently checksum/member/version verified at
https://github.com/sencoders/cloud-mini-project/releases/tag/models-v1-v2;
V2 archive upload is blocked by network timeouts; it is not available in the Release.

Normal CI passed all five jobs, with 100% JSON validity on all 100 actual predictions:
https://github.com/sencoders/cloud-mini-project/actions/runs/42029372903

The separate real-untrained-model run passed model evaluation and failed precisely
at the unchanged 95% quality gate, with 0% validity over all 100 IDs; lint/unit/secret
scan passed:
https://github.com/sencoders/cloud-mini-project/actions/runs/42030357782

Original failure: Release download returned `release not found` after a network
reset interrupted publication. No model, data, workflow or threshold change was
needed. Actual artifacts and logs: results/publication/. The remaining text below
is the preserved pre-publication local milestone, not current remote status.


The ordered workflow is `.github/workflows/ci.yml`: lint → unit → Release-backed
CPU evaluation → `score.py --min-validity 95` → gitleaks. The secret scan runs even
when preceding jobs fail. Raw predictions, scores, gate logs and the actual run URL
are uploaded as evidence. No weights are checked into Git or passed between jobs.
The actual GitHub Release archive is mandatory and must match the committed archive
and individual-file SHA-256 manifests before extraction. No local-cache fallback
is allowed. The bad-model workflow downloads/verifies that asset, then evaluates
the genuine untrained pinned Pythia-70M on all 100 validation records.

## Verified locally

- Ruff 0.14.4 critical Python correctness rules pass (`results/task6/lint.log`).
- Full unit suite: **129 passed, 1 skipped**; the optional live S3 integration test
  is skipped unless explicitly enabled. Focused release tests cover content hashes,
  tampering and path traversal; bootstrap tests guard preservation and exact teardown.
- `make up` successfully inspected the existing healthy storage and app, preserving
  the data Pod and the current one-replica HPA policy. See `make-up.log`.
- `make down-dry-run` prints `k3d cluster delete command-parser`; the command is
  unit-tested. Destructive deletion was deliberately **not executed**, because it
  would remove the user's working cluster. Fresh-clone bootstrap is implemented
  but **not end-to-end verified**: it needs a published Release and GitHub CLI.
- Actual local V1 and V2 archives: **9 verified members each**, including model,
  tokenizer, config, version metadata and manifest. Both match the public checksums
  (`release-verification.json`). They remain ignored local artifacts, not Git files.
- Re-running the supplied scorer on preserved genuine Task 2 raw predictions:
  V1 **100% JSON validity, exit 0**; untrained **0%, exit 1** at threshold 95.
  This is a real **local** gate demonstration, not a GitHub workflow run.
- The new CI evaluator also ran on all **100 actual local V1 archive records in
  12.441 seconds**; every raw completion matched the preserved Task 2 output.
  Scores remain 100/80/66/70/77/26 percent. This validates local evaluation code,
  not the still-pending GitHub download. See local-release-evaluation/.
- Gitleaks full-history first scan found six occurrences of a public Docker GPG
  fingerprint. That diagnostic is preserved. An exact-public-fingerprint exception
  is documented in `results/task6/secret-scan-notes.md`; configured history and current-source scans each reported **zero findings**,
  recorded separately in gitleaks-history-configured.json and gitleaks-current-source.json. It does not exclude secrets or whole evidence paths.

## Historical pre-publication status and rubric gaps

There is no configured Git remote. No workflows have run, no Release has been
published, and there is no failed-run URL. `results/task6/github-status.json` records
these facts. The CI evaluation/failed-GitHub-gate rubric cannot yet be demonstrated.

After repository/authentication setup and separately authorized push/publication:
1. Publish **both** verified archives and sidecars on one existing model-release
   tag; see `docs/releases.md` and `publish-release.yml` (publish defaults false).
2. Set repository variable `MODEL_RELEASE_TAG` to that tag.
3. Run the normal workflow, then dispatch `bad-model-gate.yml` with that release_tag.
4. Verify the normal gate is green, the bad-model run fails **at quality-gate**,
   and secret-scan reports zero. Put the real failed-run URL in this report.
5. Verify fresh-clone `make up` on a separate disposable environment. Verify actual
   `make down` there, never on the preserved project cluster without intent to delete.

A public Release permits bootstrap without paid APIs; private repositories need
`gh auth login`. Docker, k3d, kubectl, Python 3.12 and gh are system prerequisites.
The three fresh-clone commands, after exporting Release configuration, are:
`python3.12 -m venv .venv312`; `.venv312/bin/pip install -r requirements-service-dev.txt`;
`make up`. Bootstrap starts storage, imports the worker image, restores released
models to S3 and deploys the CPU service. It does not regenerate labels or train.

## Verified publication closeout (supersedes historical status above)

Private source and V1 Release are published at https://github.com/sencoders/cloud-mini-project and https://github.com/sencoders/cloud-mini-project/releases/tag/models-v1-v2. Normal CI passed all five jobs: https://github.com/sencoders/cloud-mini-project/actions/runs/42080057058. The real bad-model run failed only at the unchanged 95% quality gate: https://github.com/sencoders/cloud-mini-project/actions/runs/42030357782. Isolated `make down` passed; original storage was preserved. V2 archive remains absent after bounded transfer retries, so fresh-clone `make up` is still blocked/unverified. Actual final reflection has been received and reviewed. See results/final-submission/ for closeout evidence and docs/final-submission.md for ZIP/tag verification.
