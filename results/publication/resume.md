# Final submission closeout checkpoint

The real 230101089.pdf was received and visually checked on all three pages. Page 1 contains Shreeja Chaudhary, 230101089 and the correct GitHub URL. It is ZIP-only, ignored at root and copied unchanged into .local/submission-input/. Main report: seven pages/all seven tasks.

Pre-closeout master: 355c5a7459e3ffed2cd804a3898de5bd109944a3. All five normal CI jobs passed: https://github.com/sencoders/cloud-mini-project/actions/runs/42080057058
Genuine bad-model quality-gate failure: https://github.com/sencoders/cloud-mini-project/actions/runs/42030357782
Release: https://github.com/sencoders/cloud-mini-project/releases/tag/models-v1-v2

V1 verified; V2 archive still absent. Final bounded retry stopped after 45.821 seconds for slow transfer (1,376,256 bytes, curl 28). All earlier attempts remain preserved. No retraining or experiments were repeated. Fresh bootstrap and previously disclosed performance gaps remain unresolved.

Finish: commit/push checked closeout source/evidence; verify its normal CI; build make submission-zip REVIEWED=1 with clean HEAD; verify all members, source commit, reflection and report, CRC, hashes and secret exclusions. Save size/hash/manifest under ignored submission/. Then create/push final at that exact commit and verify the remote tag. NO COMMITS AFTER final. One ZIP is uploaded to the portal by the student. If interrupted, inspect git/remote/tag and submission/verification.json before doing anything; never move an existing final tag.
