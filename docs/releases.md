# Verified model release packaging

Private Release: https://github.com/sencoders/cloud-mini-project/releases/tag/models-v1-v2

V1 is published, independently downloaded, and checked against the committed archive
and every member checksum plus version metadata. V2 is still uploading; its archive
is not yet claimed remotely available. Current verification: results/publication/outcome.json.
No model weights or credentials are committed to Git.

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
Release as published. The verified current publication uses the model-specific tag above; it is not the final submission tag.

## Both-version Release for CI and fresh bootstrap

The locally verified archives have nine members each and match the committed
`models/v1/release.sha256` and `models/v2/release.sha256`. Verification evidence is
`results/task6/release-verification.json`. Each archive includes `version.json`,
`model.sha256`, weights, tokenizer and model config. Publication status and per-version checks are recorded above and in results/publication/.

`publish-release.yml` prepares **both** versions on the same release tag using a
self-hosted Mac with access to SeaweedFS. Configure its three S3 secrets; leave
`publish=false` to inspect the uploaded workflow artifact first. Actual publication
requires a configured GitHub repository, authenticated runner and an existing tag.
A locally authenticated equivalent, only after explicit publication authorization:

```sh
gh release create "$MODEL_RELEASE_TAG" --verify-tag --title 'CPU Pythia-70M V1 and V2' --notes 'Verify the committed archive and member checksums.' .local/releases/pythia-70m-v1.tar.gz .local/releases/pythia-70m-v1.tar.gz.sha256 .local/releases/pythia-70m-v2.tar.gz .local/releases/pythia-70m-v2.tar.gz.sha256
```

Set GitHub Actions variable `MODEL_RELEASE_TAG`; dispatch `ci.yml`, then
`bad-model-gate.yml` with that `release_tag`. Obtain the **actual** failed-run URL
with `gh run list --workflow bad-model-gate.yml`; verify its quality-gate step
failed with validity below 95 before citing it. Verified deliberate failure: https://github.com/sencoders/cloud-mini-project/actions/runs/42030357782 (model-evaluation passed; the unchanged 95% gate rejected the real untrained model at 0% validity).
