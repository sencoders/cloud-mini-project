"""Raw, uncorrected validation predictions and supplied score.py reports."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from training.common import CONFIG, ROOT, digest, read_config, setup_cpu, write_json
from worker.label import teacher


def evaluate(which):
    cfg = read_config()
    setup_cpu(cfg)
    rows = [json.loads(line) for line in (ROOT / cfg['evaluation']['validation_path']).read_text().splitlines()]
    if len(rows) != 100 or len({r['id'] for r in rows}) != 100:
        raise ValueError('Expected all 100 unique validation records')
    folder = ROOT / 'results/task2/evaluation'
    folder.mkdir(parents=True, exist_ok=True)
    raw_path = folder / f'{which}_raw_predictions.jsonl'
    identity = {'model': which, 'base_revision': cfg['model']['revision'],
                'config_sha256': digest(CONFIG.read_bytes()),
                'validation_sha256': digest((ROOT / cfg['evaluation']['validation_path']).read_bytes()),
                'teacher_prompt_sha256': digest((ROOT / 'prompts/teacher_prompt.txt').read_bytes())}
    if which == 'teacher':
        from training.common import local_credentials
        from worker.storage import client, get
        local_credentials()
        task1 = json.loads(get(client(), 'teacher/progress/shard-0/manifest.json'))
        if task1['prompt_sha256'] != identity['teacher_prompt_sha256']:
            raise ValueError('Teacher prompt differs from Task 1')
        with urllib.request.urlopen(cfg['evaluation']['ollama_url'] + '/api/tags', timeout=30) as response:
            tags = json.load(response)
        model_info = next(m for m in tags['models'] if m['name'] == 'phi3.5:latest')
        original = json.loads((ROOT / 'results/runtime.json').read_text())['ollama_models']['models']
        old_digest = next(m['digest'] for m in original if m['name'] == 'phi3.5:latest')
        if model_info['digest'] != old_digest:
            raise ValueError('Teacher model digest differs from Task 1')
        identity['teacher_model_digest'] = model_info['digest']
    if which == 'student_v1':
        identity['version_sha256'] = digest((ROOT / cfg['artifacts']['local_root'] / 'v1/version.json').read_bytes())
    state = folder / f'{which}_run.json'
    if state.exists() and json.loads(state.read_text()) != identity:
        raise ValueError('Evaluation configuration changed; archive prior run first')
    if raw_path.exists() and not state.exists():
        raise ValueError('Predictions without provenance cannot be resumed')
    write_json(state, identity)
    records = []
    if raw_path.exists():
        records = [json.loads(line) for line in raw_path.read_text().splitlines()]
        if [r['id'] for r in records] != [r['id'] for r in rows[:len(records)]]:
            raise ValueError('Saved predictions are not a validation prefix')
    model = tokenizer = None
    if which != 'teacher':
        from student.runtime import load_model
        source = (ROOT / cfg['model']['local_path'] if which == 'untrained'
                  else ROOT / cfg['artifacts']['local_root'] / 'v1')
        model, tokenizer = load_model(source)
    else:
        os.environ['OLLAMA_URL'] = cfg['evaluation']['ollama_url']
    started = time.perf_counter()
    prompt = (ROOT / 'prompts/teacher_prompt.txt').read_text()
    for row in rows[len(records):]:
        tick = time.perf_counter()
        if which == 'teacher':
            for attempt in range(1, 6):
                try:
                    raw = teacher(row['text'], prompt)
                    break
                except Exception as error:
                    print(json.dumps({'event': 'evaluation_retry', 'id': row['id'],
                                      'attempt': attempt, 'error': str(error)}), flush=True)
                    if attempt == 5:
                        raise
                    time.sleep(min(2 ** attempt, 30))
        else:
            from student.runtime import generate_raw
            raw = generate_raw(model, tokenizer, row['text'],
                    max_new_tokens=cfg['evaluation']['max_new_tokens'],
                    max_input_tokens=cfg['evaluation']['max_input_tokens'])
        record = {'id': row['id'], 'prediction': raw}
        records.append(record)
        with raw_path.open('a') as file:
            file.write(json.dumps(record, ensure_ascii=False) + '\n')
            file.flush()
            os.fsync(file.fileno())
        print(json.dumps({'event': 'evaluated', 'model': which, 'id': row['id'],
                          'seconds': time.perf_counter() - tick}), flush=True)
    report_path = ROOT / 'results' / f'{which}_validation.json'
    command = [sys.executable, 'tools/score.py', str(raw_path), cfg['evaluation']['validation_path'],
               '--out', str(report_path)]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    (folder / f'{which}_score.log').write_text('$ ' + ' '.join(command) + '\n' + result.stdout + result.stderr)
    if which != 'teacher':
        from student.runtime import InvalidModelOutput, extract_json
        extracted = []
        valid = 0
        for record in records:
            try:
                text, _ = extract_json(record['prediction'])
                valid += 1
            except InvalidModelOutput:
                text = record['prediction']
            extracted.append({'id': record['id'], 'prediction': text})
        derived = folder / f'{which}_extracted_predictions.jsonl'
        derived.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in extracted))
        secondary = subprocess.run([sys.executable, 'tools/score.py', str(derived),
                    cfg['evaluation']['validation_path'], '--out', str(folder / f'{which}_extracted_scores.json')],
                    cwd=ROOT, text=True, capture_output=True, check=True)
        (folder / f'{which}_extracted_score.log').write_text(secondary.stdout)
    else:
        valid = None
    write_json(folder / f'{which}_provenance.json', {
        'model': which, 'examples': len(records), 'raw_prediction_sha256': digest(raw_path.read_bytes()),
        'validation_sha256': digest((ROOT / cfg['evaluation']['validation_path']).read_bytes()),
        'teacher_prompt_sha256': digest(prompt.encode()) if which == 'teacher' else None,
        'config_sha256': digest(CONFIG.read_bytes()), 'new_evaluation_seconds': time.perf_counter() - started,
        'score_input': 'raw_predictions', 'extraction_schema_valid': valid,
        'generation': {'temperature': 0, 'seed': 42, 'num_predict': 256, 'num_ctx': 2048,
                       'format': 'json', 'stream': True} if which == 'teacher' else cfg['evaluation']})
    print(result.stdout, flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model', choices=['teacher', 'untrained', 'student_v1'], required=True)
    evaluate(ap.parse_args().model)
