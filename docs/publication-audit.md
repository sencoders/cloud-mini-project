# Pre-publication compliance audit

## Scope and decision

The audit starts from cb4249b and covers all six reachable commits, all 576 tracked
files, and all 533 distinct historical blobs (50,224,360 bytes). Every historical
file path was checked in every commit, not merely at HEAD. Reproducible inspection
code is scripts/audit_publication.py. Results and an exact file inventory are in
results/publication/. New corrections are scanned again before the first push.

**Source publication decision: SAFE TO PUBLISH to the requested private repository
once the recorded checks pass.** This does not mean every grading threshold is met
or the final submission is complete. No final tag is authorized at this stage.

- No known raw/base64 S3 credentials, kubeconfig private keys, private-key blocks,
  forbidden local/cache paths, checkpoint/weight files or unexpected binary blobs
  were found in reachable history. The only binary blobs are PDFs.
- Gitleaks defaults are retained. Its sole exception permits the exact public
  Docker GPG signing fingerprint, not a password, private key or API token. The
  original six generic matches remain in historical evidence. No genuine finding
  has been suppressed; configured history scanning reports zero.
- No Secrets containing credential data or local kubeconfig are tracked. YAML
  `secretKeyRef` references are required wiring, not credential values.
- Thirty-two historical blobs contain local user/workspace paths from genuine
  execution logs, not reusable credentials. Author identity metadata is also
  visible in Git commits. These are disclosed non-secret metadata and intentionally
  preserved with the evidence; no history rewrite is warranted by this audit.
  The requested repository and Release remain private. Broader public distribution
  would warrant a separate personal-information review.
- The 30,030,658-byte commands log is genuine UTF-8 evidence, not a model artifact.
  It is below GitHub's hard file-size limit. It is retained rather than edited to
  conceal failed commands or measurements.

## Corrections and report checks

README was consolidated to remove contradictory old setup instructions and stale
"current" test counts. Detailed milestone results remain available, explicitly
historical where relevant. AI_USE.md truthfully identifies Codex code/documentation
assistance, the required Ollama teacher, purposes, executed checks, failures and
student responsibility for the handwritten reflection. No independent human
authorship or invented verification is asserted. Ignore rules now also cover
common environment/credential variants, tooling caches and submission staging.

The seven-page report has all seven task sections. Metrics agree with preserved
score/Locust/resource evidence; estimates use the supplied rate card and stated
billing boundaries. It explicitly reports rolling errors 7.792% >0.5%, baseline
errors 1.058% >1%, a failed 99% SLO, and single-machine limitations. Archive hashes
are distinguished from per-file hashes. Remote CI/Release claims must be updated
only from actual verification; historical local-only statements are not retroactively
edited into execution claims. No fake failed-run URL or placeholder hyperlink is
used. Required shell configuration values are documented as parameters.

## Exact deliverable classification

**GitHub repository:** the exact intended path list is
`results/publication/intended-github-files.txt` (one path per file). It includes:

- Root: ASSIGNMENT.pdf, README.md, AI_USE.md, Makefile, dependency/configuration
  files, .gitignore/.dockerignore/.gitattributes, .gitleaks.toml and pyproject.toml.
- ci/, scripts/, worker/, student/, training/, service/ (including Dockerfiles),
  tests/, cluster/, network/, prompts/, .github/workflows/ and docs/.
- Unmodified supplied data/ and tools/, genuine results/, public checksum/version
  metadata only under models/, task notes and report/report.pdf under report/.
- Model weights/tokenizer payloads, private state, virtual environments and release
  archives are **not** repository content. The tokenizers exist only in model assets.

**GitHub Release assets, on a model-specific tag (never `final` in this stage):**

1. pythia-70m-v1.tar.gz
2. pythia-70m-v1.tar.gz.sha256
3. pythia-70m-v2.tar.gz
4. pythia-70m-v2.tar.gz.sha256

Each archive contains exactly nine files: config.json, generation_config.json,
model.safetensors, special_tokens_map.json, tokenizer.json, tokenizer_config.json,
training_config.yaml, version.json and model.sha256. Both archives are checked
against committed archive hashes and each member against the committed model
manifest. They include no environment files, credentials, caches or extra members.
The private repository's Release requires authentication to download.

**Separate submission / ZIP-only if the submission portal requests a ZIP:**
`<roll_number>.pdf`, the student's actual three-page handwritten reflection with
name, roll number and the real GitHub assignment URL. It is not a Release model
asset and is not generated or committed here. **The supplied ASSIGNMENT.pdf does
not explicitly require a ZIP or define other ZIP-only files**; do not invent an
archive requirement. report/report.pdf remains a repository deliverable. If a portal
requires a final ZIP, include its requested source/report/reflection copies without
.git/, .local/, environments, credentials or embedded model weights.

## Remaining grading/submission items

Actual remote Release verification, normal CI and the deliberate failed-quality-gate
URL are recorded separately as they execute. Fresh-clone bootstrap and destructive
teardown still need a disposable-environment check. The handwritten reflection and
final reviewed commit/tag remain the student's final submission actions. Threshold
gaps are documented, not concealed or reclassified as passing.

## Verified remote closeout

Private source and V1 Release are published. V1 download/member/version checks
passed. Normal CI passed all jobs at runs 42029372903 and 42034879848. The real
untrained-model run 42030357782 evaluated all 100 IDs, then failed precisely at
the unchanged 95% gate with 0% validity; its other jobs passed. Actual URLs and
artifacts are in results/publication/. V2 Release upload is blocked by recorded
transport failures; no V2 archive or complete two-version Release is claimed.
Source publication passed the safety audit; final submission remains incomplete.
