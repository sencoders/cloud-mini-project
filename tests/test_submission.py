"""Packaging safety tests; synthetic PDF fixtures are never submission scans."""
import io
from pathlib import Path
import zipfile

from pypdf import PdfWriter
import pytest

from scripts.package_submission import build, reflection_checks, safe_member


def pdf_fixture(path, pages):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    with path.open('wb') as stream:
        writer.write(stream)
    return path


@pytest.mark.parametrize('name', ['.git/config', '.local/kubeconfig', '.venv312/bin/python',
    'a/__pycache__/x.pyc', '.env.production', 'a/model.safetensors', 'a/checkpoint.pt',
    '../escape', '/absolute', 'a\\escape', 'credentials.json', 'submission/old.zip'])
def test_private_or_weight_members_rejected(name):
    assert not safe_member(name)


def test_public_metadata_and_code_allowed():
    assert all(safe_member(p) for p in ['models/v1/model.sha256', 'service/app.py',
                                      '.github/workflows/ci.yml', 'report/report.pdf', 'results/submission/latest-ci.json'])


def test_reflection_requires_exact_filename_three_pages_and_review(tmp_path):
    scan = pdf_fixture(tmp_path / '230101089.pdf', 3)
    with pytest.raises(ValueError, match='Review handwriting'):
        reflection_checks(scan, '230101089', False)
    assert reflection_checks(scan, '230101089', True)['pages'] == 3
    with pytest.raises(ValueError, match='filename'):
        reflection_checks(scan, 'other', True)
    pdf_fixture(scan, 2)
    with pytest.raises(ValueError, match='three-page'):
        reflection_checks(scan, '230101089', True)


def test_missing_reflection_blocks_final_zip(tmp_path):
    with pytest.raises(ValueError, match='missing'):
        reflection_checks(tmp_path / '230101089.pdf', '230101089', True)
    with pytest.raises(ValueError, match='blocked'):
        build(tmp_path, {'ready_to_package': False, 'errors': ['scan missing']}, '', '')


def test_zip_exact_snapshot_hashes_and_no_untracked_files(tmp_path, monkeypatch):
    import scripts.package_submission as pack
    source = io.BytesIO()
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('README.md', 'fixture source')
    monkeypatch.setattr(pack, 'git', lambda *a: source.getvalue())
    scan = pdf_fixture(tmp_path / '230101089.pdf', 3)
    info = {'ready_to_package': True, 'archive_name': '230101089.zip',
            'source_commit': 'fixture-commit', 'source_entries': ['README.md'],
            'reflection_destination': '230101089.pdf',
            'reflection': reflection_checks(scan, '230101089', True)}
    result = build(tmp_path, info, scan, tmp_path / '230101089.zip')
    assert result['crc_and_file_hashes_verified']
    with zipfile.ZipFile(result['zip']) as archive:
        assert set(archive.namelist()) == {'README.md', '230101089.pdf', 'SUBMISSION_MANIFEST.json'}
    assert Path(result['zip'] + '.sha256').is_file()
    scan.write_bytes(scan.read_bytes() + b'changed after review')
    with pytest.raises(ValueError, match='changed after review'):
        build(tmp_path, info, scan, tmp_path / 'other/230101089.zip')
