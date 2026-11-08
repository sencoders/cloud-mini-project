# Final submission: Shreeja Chaudhary, 230101089

The authoritative checklist is ASSIGNMENT.pdf Section 8 (pages 13–14).
It requires source on GitHub, model/tokenizer/version/checksum Release assets,
genuine evidence, README commands, a report of at most eight pages covering seven
tasks, the student's three-page handwritten reflection and the assessed `final`
commit/tag. **The PDF does not explicitly prescribe a ZIP**; the student additionally
requested exactly `230101089.zip`. Do not confuse a complete file archive with
meeting every rubric threshold.

## Current verified state

- Repository: https://github.com/sencoders/cloud-mini-project (private).
- Latest completed source CI at 355c5a7 passed all five jobs:
  https://github.com/sencoders/cloud-mini-project/actions/runs/42080057058
- Genuine untrained-model failure, specifically at the unchanged 95% gate:
  https://github.com/sencoders/cloud-mini-project/actions/runs/42030357782
- Release: https://github.com/sencoders/cloud-mini-project/releases/tag/models-v1-v2
  V1 is downloaded/hash/member/version verified. V2 archive upload remains blocked;
  V2 itself is intact in local storage and SeaweedFS. See results/submission/ for the
  bounded latest retry, and results/publication/ for every preceding attempt.
- Report: report/report.pdf, seven pages, seven sections, student name/roll number,
  clickable repository/Release/CI links and metrics checked against actual scores.
- The source includes Dockerfiles, infrastructure, tests, runtime, training and
  evaluation scripts, network files, AI_USE.md and genuine results.
- The real `230101089.pdf` is received: exactly three unencrypted pages, all visually reviewed as legible handwriting, with name, roll number and the correct GitHub URL on page 1. No tag is created until final archive verification.

## Required reflection: user-provided scan only

Supply **230101089.pdf**, the actual three-page handwritten reflection, containing
**Shreeja Chaudhary**, **230101089**, and the actual repository URL. The PDF requests
three pages; exactly three also satisfies the student's maximum-three-page limit.
Do not include brackets or spaces in the filename. Keep the input in
`.local/submission-input/230101089.pdf` (ignored) after receipt.

The student must write it themselves. The assistant must not fabricate handwriting,
a scan, a signature or authorship. Before enabling REVIEWED=1, visually check that
all three pages are handwritten and legible and contain the name, roll number and
repository link. Page counting alone does not prove handwriting or identity.
Synthetic PDFs used by unit tests are temporary test fixtures and never submission
artifacts. Packaging refuses a missing scan, wrong filename/page count, missing
manual review, dirty source tree, unsafe tracked file or an existing output ZIP.

## ZIP layout and exclusions

The ZIP root contains the **exact committed Git snapshot**, preserving paths such as
report/report.pdf, service/Dockerfile, cluster/, network/, training/, tests/,
results/, README.md and AI_USE.md; plus:

- `230101089.pdf`: the real reviewed scan, copied byte-for-byte.
- `SUBMISSION_MANIFEST.json`: source commit, identity, repository/Release links,
  limitations, reflection review declaration and SHA-256/size of every payload file.

No `.git/`, `.local/`, credentials, kubeconfig, environment files, virtual environments,
caches, model weights/checkpoints or nested release archives are permitted. Ignored
runtime state and arbitrary untracked files are never collected. Weights and tokenizer
payloads remain Release assets, referenced by URL; their public manifests remain in
source. The handwritten reflection and ZIP are separate submission files and are not
committed to Git. The final source commit recorded in the manifest must be the one
later tagged `final`.

## Commands — real scan received and visually verified

```sh
make submission-plan
```

This writes `.local/submission-plan.json`; inspect `errors` and `ready_to_package`.
It creates no ZIP and no tag. The initial genuine blocked plan is retained under
results/submission/initial-packaging-plan.json. Use `git status --short` and commit
only intended source/report/evidence changes before building; never stage private
input or the archive. Run the configured Gitleaks scan and relevant unit tests.

**Only after receiving and manually reviewing the actual scan**, with clean committed
source, run:

```sh
make submission-plan REVIEWED=1
make submission-zip REVIEWED=1
unzip -t submission/230101089.zip
(cd submission && shasum -a 256 -c 230101089.zip.sha256)
```

The builder uses `git archive HEAD`, refuses symlinks/private artifacts, compares its
member list with the inspected commit, and verifies every output payload and ZIP CRC.
It produces ignored `submission/230101089.zip` and its checksum sidecar. Check the
manifest's `source_commit`, presence of `230101089.pdf` and report/report.pdf, and
absence of forbidden files. Do not run `zip -r .`; that could include private state.
An old ZIP is never silently overwritten; archive it outside the output path before
an intentional rebuild. The script itself never creates or pushes any Git tag.

## Remaining release and reproducibility work

A slow-transfer-guarded V2 retry is recorded in results/submission/. If still absent,
on a faster reliable connection retry **only** the unchanged V2 archive:

```sh
gh release upload models-v1-v2 .local/releases/pythia-70m-v2.tar.gz --repo sencoders/cloud-mini-project --clobber
gh release view models-v1-v2 --repo sencoders/cloud-mini-project --json url,isDraft,assets
```

Require uploaded size 234137342 and server SHA-256
`76fc7cacaa2cbad573307fd303f3d41344295b1c18c060618c43423714b0d230`.
Verify its nine members/version metadata against models/v2/model.sha256, then update
Release title/notes and the reports to mark both versions available. A successful
V1 upload or a V2 checksum sidecar alone is not a complete V2 archive upload.
Current fresh bootstrap needs both versions, so missing V2 also blocks that path.
Fresh-clone make up remains blocked/unverified. Real make down was verified on a
separate disposable cluster via the explicit CLUSTER_NAME override, preserving the
working cluster and SeaweedFS. Default teardown still deletes command-parser; do not
execute it unintentionally. See results/final-audit/isolated-teardown.json.

Measured rolling errors 7.792% exceed 0.5%; baseline errors 1.058% exceed 1%, and the
99% success SLO was not met. These remain disclosed grading gaps; packaging does
not repair or conceal them. Private repository/Release access must be available to
the assessor through the student's access settings.

## Final tag — after archive verification

Do **not** execute these until the real reflection, mandatory files, ZIP checks,
source/Release evidence and intended final commit have been reviewed. The student has authorized final-tag creation after those checks pass. Once ready, the intended
commands are:

```sh
git status --short
git push origin master
git tag final
git push origin final
```

Confirm HEAD equals SUBMISSION_MANIFEST.json's source_commit **before** tagging.
Review successful CI for that source commit and ensure `final` does not already
exist. Never move/force-push an existing assessed final tag. The student explicitly requests a one-ZIP submission: upload `submission/230101089.zip`, with `230101089.pdf` at its root, to the instructor's portal before the
actual deadline; creating a ZIP or tag alone does not submit a portal upload.

## Final closeout evidence

See `results/final-submission/`: real scan review/hash, seven-page report and link checks, full-history secret/credential audit, 154 passing tests (one optional integration skip), and actual CI/Release responses. A final bounded V2 retry stopped after 45.821 s: 1,376,256 bytes at 30,086 B/s, curl exit 28 (slow transfer). V2 remains unpublished; no full fresh-clone deployment is claimed. ZIP size, SHA-256, extracted manifest and remote tag verification are saved under ignored `submission/` after the final source commit, avoiding a self-referential archive. No commit may follow the final tag.
