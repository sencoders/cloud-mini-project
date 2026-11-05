# Publication closeout / resume

Private source: https://github.com/sencoders/cloud-mini-project
Master at b695db6834c833b497ba7e4b230e7d8d21b4b30c before the closeout commit.
No final tag exists. Core model/training/data/workflow code remains unchanged.

Published V1: https://github.com/sencoders/cloud-mini-project/releases/tag/models-v1-v2
V1 was downloaded and archive/member/version hashes verified. Only V1 and the
two checksum sidecars exist; V2 archive is NOT uploaded. V2 remains intact in
SeaweedFS and .local/releases/.

Normal CI passed all five jobs:
https://github.com/sencoders/cloud-mini-project/actions/runs/42029372903
The pushed evidence commit also passed:
https://github.com/sencoders/cloud-mini-project/actions/runs/42034879848
Genuine deliberate failure (only quality-gate failed, 0% validity, all 100 IDs):
https://github.com/sencoders/cloud-mini-project/actions/runs/42030357782
Logs, predictions, scores and zero-finding scans are committed under this directory.

V2 is BLOCKED by transfer failures. Two retries returned HTTP 408; the third
client was stopped after measured 77 minutes without asset completion. A bounded
HTTP/1.1 request timed out after 600 s, having sent 30,670,848 bytes at 51,117 B/s.
No upload is active. On a faster reliable uplink, retry only:

```sh
gh release upload models-v1-v2 .local/releases/pythia-70m-v2.tar.gz --repo sencoders/cloud-mini-project --clobber
gh release view models-v1-v2 --repo sencoders/cloud-mini-project --json url,isDraft,assets
```

Require V2 state uploaded, 234137342 bytes, SHA-256
76fc7cacaa2cbad573307fd303f3d41344295b1c18c060618c43423714b0d230
before marking both versions complete or changing the pending-V2 title/notes.
Do not retrain, regenerate labels, weaken the 95% gate or create final.
