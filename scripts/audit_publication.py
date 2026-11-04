"""Audit all reachable Git history; never print credential values or modify refs."""
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/publication'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def forbidden(path):
    parts = Path(path).parts
    return (any(x in {'.local', '.venv', '.venv312', '__pycache__', '.pytest_cache', '.aws', '.ruff_cache'}
                or x.startswith('.venv-') for x in parts)
            or path.endswith(('.safetensors', '.bin', '.pt', '.pth', '.ckpt', '.onnx', '.pem', '.key', '.whl', '.tar.gz', '.zip'))
            or Path(path).name in {'.env', 'kubeconfig', 'credentials.json'}
            or Path(path).name.startswith('.env.'))


def main():
    OUT.mkdir(exist_ok=True)
    commits = git('rev-list', '--all').decode().splitlines()
    paths = git('ls-files', '-z').decode().split('\0')[:-1]
    blobs = {}
    forbidden_paths = []
    for commit in commits:
        for entry in git('ls-tree', '-rz', '--long', commit).split(b'\0'):
            if not entry:
                continue
            info, path = entry.split(b'\t', 1)
            mode, kind, oid, size = info.decode().split()
            path = path.decode()
            if forbidden(path):
                forbidden_paths.append({'commit': commit, 'path': path})
            if kind == 'blob':
                record = blobs.setdefault(oid, {'paths': set(), 'bytes': int(size)})
                record['paths'].add(path)
    known = []
    credentials = ROOT / '.local/credentials.json'
    if credentials.exists():
        for value in json.loads(credentials.read_text()).values():
            known.extend([value.encode(), base64.b64encode(value.encode())])
    kubeconfig = ROOT / '.local/kubeconfig'
    if kubeconfig.exists():
        for value in re.findall(r'client-key-data:\s*(\S+)', kubeconfig.read_text()):
            known.extend([value.encode(), base64.b64decode(value)])
    process = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    inventory, findings, private_paths, binary_files, credential_fields = [], [], [], [], []
    for oid, record in blobs.items():
        process.stdin.write((oid + '\n').encode())
        process.stdin.flush()
        header = process.stdout.readline().decode().split()
        raw = process.stdout.read(int(header[2]))
        process.stdout.read(1)
        paths_for_blob = sorted(record['paths'])
        item = {'oid': oid, 'paths': paths_for_blob, 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest()}
        inventory.append(item)
        if any(value in raw for value in known):
            findings.append({'oid': oid, 'paths': paths_for_blob, 'kind': 'known raw/base64 credential or private key'})
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\r\n]+[A-Za-z0-9+/=]{30}', raw):
            findings.append({'oid': oid, 'paths': paths_for_blob, 'kind': 'PEM private key material'})
        if re.search(rb'/Users/[^/\s"<>]+|/home/[^/\s"<>]+|/private/var/', raw):
            private_paths.append({'oid': oid, 'paths': paths_for_blob})
        if re.search(rb'"(?:AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|client-key-data|accessKey|secretKey)"\s*:\s*"[^"\n]+"', raw):
            credential_fields.append({'oid': oid, 'paths': paths_for_blob})
        if b'\x00' in raw:
            binary_files.append({'oid': oid, 'paths': paths_for_blob, 'pdf_magic': raw.startswith(b'%PDF-')})
            if not raw.startswith(b'%PDF-'):
                findings.append({'oid': oid, 'paths': paths_for_blob, 'kind': 'unexpected binary file; inspect before publication'})
    process.stdin.close()
    process.wait()
    (OUT / 'tracked-files.txt').write_text('\n'.join(paths) + '\n')
    (OUT / 'history-blob-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    (OUT / 'private-path-inventory.json').write_text(json.dumps(private_paths, indent=2) + '\n')
    summary = {'audited_head': git('rev-parse', 'HEAD').decode().strip(),
        'commits': len(commits), 'tracked_files': len(paths), 'distinct_history_blobs': len(inventory),
        'bytes_inspected': sum(r['bytes'] for r in inventory), 'credential_or_unexpected_binary_findings': findings,
        'forbidden_paths_in_any_commit': forbidden_paths,
        'historical_blobs_with_local_user_paths': len(private_paths),
        'literal_credential_fields_for_review': credential_fields, 'binary_files': binary_files,
        'largest_blobs': sorted(inventory, key=lambda x: x['bytes'], reverse=True)[:8]}
    (OUT / 'history-audit.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in {'largest_blobs', 'binary_files'}}, indent=2))
    if findings or forbidden_paths:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
