"""Plan or build a source-only submission ZIP; never create or push a Git tag."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'https://github.com/sencoders/cloud-mini-project'
RELEASE = REPOSITORY + '/releases/tag/models-v1-v2'
REQUIRED = ('README.md', 'AI_USE.md', 'Makefile', 'ASSIGNMENT.pdf',
            'training/config.yaml', 'training/loss.csv', 'training/train.py',
            'training/evaluate.py', 'training/artifacts.py', 'student/runtime.py',
            'worker/label.py', 'worker/clean.py', 'worker/storage.py',
            'service/app.py', 'service/storage.py',
            'service/Dockerfile', 'worker/Dockerfile', 'cluster/k3d.yaml',
            'cluster/app.yaml', 'cluster/hpa.yaml', 'network/subnets.md',
            'network/nacl.json', 'prompts/teacher_prompt.txt',
            '.github/workflows/ci.yml', '.github/workflows/bad-model-gate.yml',
            'report/report.pdf', 'results/teacher_validation.json',
            'results/untrained_validation.json', 'results/student_v1_validation.json')
PREFIXES = ('tests/', 'training/', 'worker/', 'service/', 'scripts/', 'tools/',
            'data/', 'results/', 'network/', 'cluster/')
FORBIDDEN_PARTS = {'.git', '.local', '.aws', '__pycache__', '.pytest_cache',
                   '.ruff_cache', 'htmlcov', 'node_modules'}
FORBIDDEN_SUFFIXES = ('.safetensors', '.bin', '.pt', '.pth', '.ckpt', '.onnx',
                      '.pem', '.key', '.p12', '.pfx', '.whl', '.pyc', '.zip', '.tar.gz',
                      '.pkl', '.pickle', '.gguf', '.ggml', '.npy', '.npz', '.h5', '.hdf5')


def safe_member(name):
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or '..' in path.parts or '\\' in name or path.parts[0] == 'submission':
        return False
    if any(p in FORBIDDEN_PARTS or p.startswith('.venv') for p in path.parts):
        return False
    if path.name in {'.env', '.envrc', '.netrc', '.pypirc', 'kubeconfig', 'credentials.json', '.DS_Store', '.coverage'}:
        return False
    return not path.name.startswith(('.env.', 'kubeconfig.')) and not name.endswith(FORBIDDEN_SUFFIXES)


def report_checks(raw):
    reader = PdfReader(io.BytesIO(raw))
    text = '\n'.join(p.extract_text() or '' for p in reader.pages)
    if not 1 <= len(reader.pages) <= 8:
        raise ValueError('Report must have at most eight pages')
    if not all(re.search(rf'\bTask\s+{n}\b', text) for n in range(1, 8)):
        raise ValueError('Report must contain all seven task sections')
    return {'pages': len(reader.pages), 'seven_sections': True}


def reflection_checks(path, roll_number, reviewed):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', roll_number):
        raise ValueError('Roll number must contain only letters, digits, underscores or hyphens')
    path = Path(path)
    if path.name != roll_number + '.pdf':
        raise ValueError('Reflection filename must be exactly <roll_number>.pdf')
    if not path.is_file():
        raise ValueError('Actual handwritten reflection scan is missing')
    reader = PdfReader(str(path))
    if reader.is_encrypted or len(reader.pages) != 3:
        raise ValueError('Assignment requires an unencrypted three-page handwritten reflection')
    if not reviewed:
        raise ValueError('Review handwriting, legibility, name, roll number and repository URL before packaging')
    return {'filename': path.name, 'pages': 3,
            'handwriting_and_identity_manually_reviewed': True,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def plan(root, roll_number, reflection, reviewed=False):
    root = Path(root)
    commit = git(root, 'rev-parse', 'HEAD').decode().strip()
    names = git(root, 'ls-tree', '-r', '--name-only', '-z', 'HEAD').decode().split('\0')[:-1]
    errors = []
    dirty = git(root, 'status', '--porcelain', '--untracked-files=normal').decode().splitlines()
    if dirty:
        errors.append('Commit intended source/evidence first; working tree is not clean')
    forbidden = [n for n in names if not safe_member(n)]
    if forbidden:
        errors.append('Forbidden tracked archive members: ' + ', '.join(forbidden))
    missing = [n for n in REQUIRED if n not in names]
    missing += [p for p in PREFIXES if not any(n.startswith(p) for n in names)]
    if missing:
        errors.append('Missing source/report/evidence: ' + ', '.join(missing))
    check = None
    if 'report/report.pdf' in names:
        try:
            check = report_checks(git(root, 'show', 'HEAD:report/report.pdf'))
        except ValueError as error:
            errors.append(str(error))
    reflection_info = None
    try:
        reflection_info = reflection_checks(reflection, roll_number, reviewed)
    except (ValueError, OSError) as error:
        errors.append(str(error))
    return {'archive_name': roll_number + '.zip', 'source_commit': commit,
            'student_name': 'Shreeja Chaudhary', 'roll_number': roll_number,
            'repository_url': REPOSITORY, 'release_url': RELEASE,
            'pdf_requires_zip': False, 'zip_requested_by_student': True,
            'source_entries': names, 'reflection': reflection_info,
            'reflection_destination': roll_number + '.pdf', 'report': check,
            'errors': errors, 'ready_to_package': not errors,
            'all_rubric_thresholds_met': False,
            'limitations': ['Rolling failures 7.792% exceed 0.5%',
                            'Baseline failures 1.058% exceed 1%; 99% SLO not met',
                            'Fresh-clone deployment/destructive teardown not end-to-end verified',
                            'Check current V2 Release availability in results/submission/']}


def build(root, plan_info, reflection, destination):
    if not plan_info['ready_to_package']:
        raise ValueError('Submission is blocked: ' + '; '.join(plan_info['errors']))
    root, destination = Path(root), Path(destination)
    if destination.name != plan_info['archive_name']:
        raise ValueError('ZIP filename must be exactly <roll_number>.zip')
    if destination.exists():
        raise FileExistsError('Refusing to overwrite an existing submission ZIP')
    # A committed HEAD archive includes exactly its snapshot, never working-tree
    # caches/untracked credentials. git archive's export-ignore attributes apply.
    source = git(root, 'archive', '--format=zip', plan_info['source_commit'])
    members = []
    with zipfile.ZipFile(io.BytesIO(source)) as original:
        for info in original.infolist():
            if info.is_dir():
                continue
            if not safe_member(info.filename) or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Unsafe or symlink archive member: ' + info.filename)
            members.append((info.filename, original.read(info)))
    expected = set(plan_info['source_entries'])
    if {n for n, _ in members} != expected:
        raise ValueError('git archive does not match the inspected committed file list')
    reflection_raw = Path(reflection).read_bytes()
    if hashlib.sha256(reflection_raw).hexdigest() != plan_info['reflection']['sha256']:
        raise ValueError('Reflection changed after review/inspection')
    members.append((plan_info['reflection_destination'], reflection_raw))
    manifest = {k: v for k, v in plan_info.items() if k != 'source_entries'}
    manifest['files'] = [{'path': n, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                         for n, raw in members]
    manifest_name = 'SUBMISSION_MANIFEST.json'
    if manifest_name in expected or plan_info['reflection_destination'] in expected:
        raise ValueError('Generated manifest/reflection must not conflict with committed source')
    members.append((manifest_name, (json.dumps(manifest, indent=2) + '\n').encode()))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in members:
            archive.writestr(name, raw)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC verification failed')
        assert set(archive.namelist()) == {n for n, _ in members}
        for name, raw in members:
            assert hashlib.sha256(archive.read(name)).digest() == hashlib.sha256(raw).digest()
    with destination.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    destination.with_suffix('.zip.sha256').write_text(checksum + '  ' + destination.name + '\n')
    return {'zip': str(destination), 'sha256': checksum, 'files': len(members),
            'source_commit': plan_info['source_commit'], 'crc_and_file_hashes_verified': True,
            'tag_created': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roll-number', default='230101089')
    parser.add_argument('--reflection', default='.local/submission-input/230101089.pdf')
    parser.add_argument('--reflection-reviewed', action='store_true')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--plan-output')
    parser.add_argument('--output', default='submission/230101089.zip')
    args = parser.parse_args()
    info = plan(ROOT, args.roll_number, args.reflection, args.reflection_reviewed)
    if args.plan_output:
        target = Path(args.plan_output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(info, indent=2) + '\n')
    if args.plan:
        print(json.dumps(info, indent=2))
        return
    print(json.dumps(build(ROOT, info, args.reflection, args.output), indent=2))


if __name__ == '__main__':
    main()
