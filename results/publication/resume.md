# Publication resume state

Source is private at https://github.com/sencoders/cloud-mini-project on master,
17cbb49745026a4c0b2221c79708bf9fa8fcd0b9. The audit passed. No final tag exists.

Initial run 41866415146 failed specifically at model-evaluation / Download actual
published Release asset (no fallback): `release not found`. Lint, unit and
secret-scan passed; quality-gate was skipped. Actual logs are
confirmed-model-evaluation-failure.log. The previous combined archive upload
failed with connection reset by peer and its Release was removed.

A fresh models-v1-v2 draft was created. Both checksum sidecars uploaded. The
verified V1 archive is uploading sequentially; do not start a duplicate upload.
Inspect release-v1-upload.log and `gh release view models-v1-v2 --repo
sencoders/cloud-mini-project --json url,isDraft,assets`. After V1 succeeds, upload
V2 separately, verify all four asset sizes/digests, publish the draft, and run
normal CI and the deliberate bad-model workflow with release_tag=models-v1-v2.

Save actual pass/failure URLs and logs, update the seven-page report, scan, commit
and push necessary evidence. Never weaken the gate, retrain, or create final.
