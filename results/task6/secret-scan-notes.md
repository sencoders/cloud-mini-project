# Secret scan findings and scope

Gitleaks 8.24.3 was downloaded from its official release and checked against its
published SHA-256 list (gitleaks-download.json). The first unconfigured full-history
scan reported six generic-api-key matches, preserved in gitleaks-history.json/log.
Every match is `GPG_KEY=7169605F62C751356D054A26A821E680E5FA6305`, the **public
signing fingerprint** exposed in the Python Docker image's Config.Env, copied into
actual Docker inspection evidence. It is not a private key, API token or S3 secret.

.gitleaks.toml retains all default rules and permits only that exact fingerprint
when preceded by GPG_KEY=. No paths, other keys or evidence directories are excluded.
The configured history and current tracked/source-file scans are saved separately.
The ignored local caches, credentials, kubeconfig and model weights are not Git
content and are intentionally not copied into the current-source scan snapshot.
All scanner output uses redaction. Zero findings is scoped to these configured
scans, not a guarantee that the system has no security weaknesses.

The first custom-config attempt used a global array form not supported by pinned
8.24.3; its unchanged six findings are retained as gitleaks-config-syntax-diagnostic.*.
The corrected documented `[allowlist]` syntax yielded zero history findings.
Version-specific syntax source: https://github.com/gitleaks/gitleaks/blob/v8.24.3/README.md#configuration
