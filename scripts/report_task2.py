#!/usr/bin/env python3
"""Build the Task 2 report from actual saved measurements and score.py outputs."""
import csv
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text())


def timed(path):
    text = (ROOT / path).read_text()
    wall = re.search(r'^\s*([0-9.]+) real', text, re.MULTILINE)
    rss = re.search(r'^\s*(\d+)\s+maximum resident set size', text, re.MULTILINE)
    if not wall or not rss:
        raise ValueError(f'No genuine time measurements in {path}')
    return {'whole_command_seconds': float(wall[1]), 'maximum_rss_bytes': int(rss[1])}


smoke = read('results/task2/smoke-latest.json')
v1 = read('results/task2/v1/summary.json')
v2 = read('results/task2/v2/summary.json')
versions = {'smoke': smoke, 'v1': v1, 'v2': v2}
timings = {name: timed(f'results/task2/{filename}') for name, filename in (
    ('smoke', 'smoke-timed-command.log'), ('v1', 'v1-command.log'), ('v2', 'v2-command.log'))}
metrics = {name: read(f'results/{name}_validation.json') for name in ('teacher', 'untrained', 'student_v1')}
for name, report in metrics.items():
    assert report['examples'] == 100 and report['missing_predictions'] == 0
    rows = [json.loads(line) for line in (ROOT / f'results/task2/evaluation/{name}_raw_predictions.jsonl').read_text().splitlines()]
    assert len(rows) == len({r['id'] for r in rows}) == 100
for version in ('v1', 'v2'):
    assert read(f'results/task2/{version}/s3-upload.json')['all_files_readback_verified']
    assert versions[version]['subset'] == 1500 and versions[version]['device'] == 'cpu'
    assert versions[version]['checkpoint_reload_passed']
assert v1['selected_source_sha256'] == v2['selected_source_sha256']
with (ROOT / 'training/loss.csv').open() as file:
    loss = list(csv.DictReader(file))
assert len(loss) == 4 and [r['version'] for r in loss] == ['v1', 'v1', 'v1', 'v2']
assert [float(r['loss']) for r in loss] == [r['loss'] for r in v1['epochs'] + v2['epochs']]
tests = (ROOT / 'results/task2/all-tests-live.log').read_text()
passed = int(re.search(r'(\d+) passed', tests)[1])
summary = {'status': 'training_evaluation_and_local_packaging_complete', 'tests_passed': passed,
           'timings': timings, 'metrics_raw': metrics,
           'task1_dataset_sha256': v1['dataset_sha256'],
           'training_records': 1500, 'last_training_id': v1['last_id'],
           'v1_total_epochs': v1['total_epochs'], 'v2_total_epochs': v2['total_epochs'],
           'release_published': False, 'source_hardware': read('results/task2/inspection.json')['cpu']}
(ROOT / 'results/task2/summary.json').write_text(json.dumps(summary, indent=2) + '\n')
lines = ['# Task 2 measured results', '',
         'CPU-only full fine-tuning of exactly EleutherAI/pythia-70m; no adapters or substitute student.',
         'The execution Mac reports ' + summary['source_hardware'] + '. Python 3.12.16; exact libraries and the source revision are in training/config.yaml.', '',
         '## Training and artifacts', '',
         '| Run | Records | Epochs | Whole command (s) | Training loop (s) | Steps/s | Peak RSS (GiB) |',
         '|---|---:|---:|---:|---:|---:|---:|']
for name, r in versions.items():
    t = timings[name]
    lines.append(f"| {name} | {r['subset']} | {r['epochs_this_run']} | {t['whole_command_seconds']:.2f} | {r['training_seconds']:.3f} | {r['steps_per_second']:.3f} | {t['maximum_rss_bytes'] / 2**30:.3f} |")
lines += ['', 'V1 uses three epochs from the base checkpoint. V2 uses one additional epoch from V1 with a fresh AdamW optimizer (four cumulative epochs). Both use the same first 1,500 cleaned records, C0001 through ' + v1['last_id'] + ', in verified ID order before deterministic epoch shuffling.',
          'The exact teacher_raw strings are targets; command and padding loss are masked, real EOS is supervised, and no sequence was truncated.',
          'The dataset SHA-256 is `' + v1['dataset_sha256'] + '`. No provided validation text overlaps the selected training commands; no validation labels are used for training.',
          'Two independent 50-example runs produced identical model weights and epoch losses (results/task2/smoke-reproducibility.json). The initial smoke rate predicted about 150.15 seconds of V1 training and 50.05 seconds of V2 training; these were estimates, separately recorded before full runs.', '',
          'All model/tokenizer/config/version files were uploaded to `s3://models/v1/` and `s3://models/v2/`, read back byte for byte, downloaded into separate local directories, and loaded on CPU. The per-file manifests are `models/v1/model.sha256` and `models/v2/model.sha256` in the bucket and repository. Weight-file hashes differ between V1 and V2.', '',
          '## Validation: exact raw-output score.py metrics (%)', '',
          '| Model | JSON validity | Intent | Date | Time | Place | Full frame |',
          '|---|---:|---:|---:|---:|---:|---:|']
keys = ('json_validity', 'intent_accuracy', 'date_accuracy', 'time_accuracy', 'place_accuracy', 'full_frame')
for name, r in metrics.items():
    lines.append('| ' + name + ' | ' + ' | '.join(f'{r[k]:.2f}' for k in keys) + ' |')
lines += ['', 'Every report covers all 100 IDs with zero missing predictions. The teacher used the exact Task 1 prompt hash, phi3.5 model digest, temperature 0, seed 42, JSON mode, 2,048 context tokens and a 256-token output bound.',
          'Student and untrained generation are greedy CPU decoding, bounded at 128 new tokens with EOS handling. Primary metrics score untouched completion text; no extraction, repair, fallback frame or gold label is substituted. Lossless extraction results are saved separately and are not the table above.',
          'The untrained model produced no valid command frames. Distillation improved JSON syntax to 100% on this validation set and intent accuracy to 80%, but student full-frame accuracy is 26% versus the teacher\'s 44%. Slot correctness remains limited; high null-slot accuracy and valid formatting are not evidence of complete semantic understanding. Validation results do not establish hidden-test performance or a deployed-service SLO.', '',
          '## Reproducibility and publication status', '',
          f'{passed} tests passed, including live S3 operations, dataset selection/checksum guards, completion/padding/EOS masks, generation bounds, JSON validation, artifact tampering checks and rejection of smoke artifacts for publishing.',
          'The original Task 1 dataset remains unchanged, and SeaweedFS and its existing buckets were neither restarted nor deleted during Task 2.',
          'Verified local Release archives exist under `.local/releases/`; the archives contain the same files described by the S3 manifests. Each archive has a separate SHA-256 sidecar. No GitHub Release has been published. No Git remote is configured, and no Git commits have been pushed. The manual packaging/publication workflow and prerequisites are in docs/releases.md. Publication requires a GitHub repository, an existing remote tag, runner/network access to SeaweedFS, and explicit publication authorization.',
          'The sequence-level versus logit-based explanation, suitability assessment and limitations are in docs/distillation.md. Tasks 3 onward were not started.']
(ROOT / 'report/task2-results.md').write_text('\n'.join(lines) + '\n')
print(json.dumps(summary, indent=2))
