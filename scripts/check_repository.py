#!/usr/bin/env python3
"""Verify supplied-file integrity and absence of generated credentials in artifacts."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {'.git', '.local', '.venv', '.venv312', '__pycache__', '.pytest_cache'}


def check():
    original = json.loads((ROOT / 'results/supplied-files.sha256.json').read_text())
    changed = [p for p, expected in original.items()
               if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != expected]
    sensitive = []
    credentials = ROOT / '.local/credentials.json'
    if credentials.exists():
        sensitive.extend(v.encode() for v in json.loads(credentials.read_text()).values())
    kubeconfig = ROOT / '.local/kubeconfig'
    if kubeconfig.exists():
        sensitive.extend(v.encode() for v in re.findall(
            r'client-key-data:\s*(\S+)', kubeconfig.read_text()))
    findings = []
    checked = 0
    for p in ROOT.rglob('*'):
        if not p.is_file() or any(part in IGNORED for part in p.relative_to(ROOT).parts):
            continue
        content = p.read_bytes()
        checked += 1
        if any(value in content for value in sensitive):
            findings.append(str(p.relative_to(ROOT)))
    report = {'supplied_files_checked': len(original), 'changed_supplied_files': changed,
              'artifact_files_scanned': checked, 'generated_credential_findings': findings,
              'scope': 'Generated S3 credentials and Kubernetes private key; not a general-purpose secret scanner'}
    (ROOT / 'results/repository-check.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if changed or findings:
        raise SystemExit(1)


if __name__ == '__main__':
    check()
