# Publication resume state

Private repo: https://github.com/sencoders/cloud-mini-project; master at
68333d74b6e6d911108b74e638868e0821e4ba00. No final tag exists.

Release: https://github.com/sencoders/cloud-mini-project/releases/tag/models-v1-v2
is published. V1 and both sidecars are available. V1 was independently downloaded,
archive/member hashes and version metadata matched committed manifests. V2 is
explicitly marked upload pending. Prior V2 attempts failed with HTTP 408 during
connection loss; user confirmed stable connection and attempt 3 is active. Do not
start a duplicate upload. See release-v2-attempt-3.log.

Normal CI PASSED all five jobs:
https://github.com/sencoders/cloud-mini-project/actions/runs/42029372903
Artifacts/logs are normal-ci-artifacts/ and normal-ci-full.log; scores
100/80/66/70/77/26, 100 IDs, raw predictions exactly match Task 2.

Separate bad-model run is in progress (not yet verified gate failure):
https://github.com/sencoders/cloud-mini-project/actions/runs/42030357782
Check actual job conclusions and download quality-gate-evidence after completion.
Require model-evaluation success, quality-gate failure and validity below 95 before
claiming the demonstration. Finish V2 upload/checksums, update Release title/notes,
update report and evidence, scan, commit/push corrections. Do not retrain or tag final.
