# Verified model release packaging

No GitHub Release is claimed to exist. Task 2 creates local, ignored archives
and records `published: false` until a real publication is independently verified.
No weights are added to Git. A public Release would expose the packaged model
and tokenizer; do not include credentials or the private `.local/` directory.

After full training and S3 upload:

```sh
make package-model VERSION=v1
make package-model VERSION=v2
```

Each deterministic archive contains model.safetensors, the model and generation
configurations, tokenizer files, version.json, the authoritative training config,
and model.sha256. Every archive member is checked against the exact same
per-file checksum manifest uploaded to `s3://models/v1/model.sha256` (or v2).
The archive has its own `.tar.gz.sha256` sidecar; an archive hash differs from the
hash of an individual weight file. Extraction followed by `shasum -a 256 -c
model.sha256` verifies the files described by the assignment's manifest.

To reproduce a package using S3 rather than a training checkout:

```sh
.venv312/bin/python -m training.artifacts download --version v1 --destination .local/models/v1
make package-model VERSION=v1
```

The manual `.github/workflows/package-model.yml` workflow performs that download,
checksums and packaging, then saves a GitHub Actions artifact. It requires a
self-hosted macOS ARM64 runner with Python 3.12 that can reach SeaweedFS, plus
repository secrets `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`. Laptop-local
SeaweedFS is not reachable from ordinary GitHub-hosted runners. Secrets are read
from environment variables and never written into package metadata.

Publishing is an explicit workflow-dispatch boolean, default false. When enabled,
provide an existing pushed tag and install GitHub CLI (`gh`) on the runner. The workflow runs `gh release create --verify-tag`
and uploads the archive, its checksum sidecar and the model checksum manifest.
It does not push Git commits or create remote tags. `gh release view TAG --json
url,assets` and a downloaded asset checksum are required before reporting a
Release as published. This project run does not execute that publication step.
