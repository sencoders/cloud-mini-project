"""Reproducible CPU-only, completion-loss distillation from verified Task 1 data."""
import argparse
import csv
import datetime
import gc
import json
import math
from pathlib import Path
import platform
import resource
import subprocess
import sys
import threading
import time

import psutil
import torch
from torch.utils.data import DataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer

from training.common import CONFIG, ROOT, digest, read_config, setup_cpu, write_json
from training.data import CompletionCollator, download_records, encode_example



def allocate_run_paths(output, results, smoke, stamp):
    """Protect real checkpoints; archive committed evidence in a fresh clone."""
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite checkpoint {output}')
    if results.exists():
        if smoke:
            raise FileExistsError(f'Smoke run ID already exists: {results}')
        history = results.parent / 'history' / f'{results.name}-{stamp}'
        history.parent.mkdir(parents=True, exist_ok=True)
        results.rename(history)
        print(json.dumps({'event': 'prior_evidence_archived', 'path': str(history)}), flush=True)


def run(version='v1', subset=None):
    cfg = read_config()
    setup_cpu(cfg)
    if version not in cfg['versions']:
        raise ValueError('Unknown version')
    smoke = subset is not None
    if smoke and (version != 'v1' or not 1 <= subset <= 1500):
        raise ValueError('SUBSET must be 1..1500 and uses the base/v1 recipe')
    count = subset if smoke else cfg['training']['max_examples']
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run_id = f'smoke-{count}-{stamp}' if smoke else version
    results = ROOT / cfg['artifacts']['results_root'] / run_id
    output = (ROOT / cfg['artifacts']['smoke_root'] / run_id / 'model' if smoke
              else ROOT / cfg['artifacts']['local_root'] / version)
    allocate_run_paths(output, results, smoke, stamp)
    results.mkdir(parents=True)
    started = time.perf_counter()
    process = psutil.Process()
    samples = []
    stopped = threading.Event()

    def monitor():
        while not stopped.wait(0.1):
            samples.append(process.memory_info().rss)

    observer = threading.Thread(target=monitor, daemon=True)
    observer.start()
    try:
        rows, data_info = download_records(cfg, count, results)
        init = cfg['versions'][version]['initialize']
        if init == 'base':
            required = ['config.json', 'tokenizer.json', 'tokenizer_config.json',
                        'special_tokens_map.json', 'model.safetensors']
            if not all((ROOT / cfg['model']['local_path'] / name).is_file() for name in required):
                subprocess.run([sys.executable, str(ROOT / 'scripts/download_student.py')],
                               cwd=ROOT, check=True)
            downloaded = json.loads((ROOT / 'results/task2/base-download.json').read_text())
            if downloaded['revision'] != cfg['model']['revision'] or downloaded['repo'] != cfg['model']['name']:
                raise ValueError('Downloaded base revision differs from configuration')
            for name, info in downloaded['files'].items():
                if digest((ROOT / cfg['model']['local_path'] / name).read_bytes()) != info['sha256']:
                    raise ValueError('Base checkpoint checksum mismatch')
        source = (ROOT / cfg['model']['local_path'] if init == 'base' else
                  ROOT / cfg['artifacts']['local_root'] / init)
        parent = None
        if init != 'base':
            from training.artifacts import verify_directory
            verify_directory(source)
            parent = json.loads((source / 'version.json').read_text())
            if parent['subset'] != 1500 or parent['smoke'] or parent['status'] != 'complete':
                raise ValueError('v2 requires a complete full v1 checkpoint')
            if parent['dataset_sha256'] != data_info['dataset_sha256']:
                raise ValueError('Parent dataset differs')
        tokenizer = AutoTokenizer.from_pretrained(source, local_files_only=True)
        if not tokenizer.is_fast:
            raise ValueError('Offset-based prompt masking requires a fast tokenizer')
        tokenizer.pad_token = tokenizer.eos_token
        encoded = [encode_example(r, tokenizer, cfg['training']['max_sequence_length']) for r in rows]
        write_json(results / 'tokenization.json', {'examples': len(encoded),
                    'min_tokens': min(len(r['input_ids']) for r in encoded),
                    'max_tokens': max(len(r['input_ids']) for r in encoded),
                    'mean_tokens': sum(len(r['input_ids']) for r in encoded) / len(encoded),
                    'truncated_examples': 0, 'prompt_loss_masked': True, 'padding_loss_masked': True})
        model = AutoModelForCausalLM.from_pretrained(source, local_files_only=True,
                    torch_dtype=torch.float32, attn_implementation='eager').to('cpu')
        model.config.use_cache = False
        model.config.pad_token_id = tokenizer.pad_token_id
        assert all(p.device.type == 'cpu' and p.dtype == torch.float32 for p in model.parameters())
        optimizer = torch.optim.AdamW(model.parameters(), lr=cfg['training']['learning_rate'],
                    betas=tuple(cfg['training']['betas']), eps=cfg['training']['epsilon'],
                    weight_decay=cfg['training']['weight_decay'])
        generator = torch.Generator(device='cpu').manual_seed(cfg['training']['seed'])
        loader = DataLoader(encoded, batch_size=cfg['training']['batch_size'], shuffle=True,
                    generator=generator, num_workers=0, collate_fn=CompletionCollator(tokenizer.pad_token_id))
        epochs = cfg['versions'][version]['epochs']
        if version == 'v1' and epochs != cfg['training']['epochs']:
            raise ValueError('v1 epoch count must match training.epochs')
        losses = []
        steps = 0
        total_train = 0.0
        step_log = (results / 'steps.jsonl').open('w')
        model.train()
        for epoch in range(1, epochs + 1):
            epoch_start = time.perf_counter()
            token_loss = 0.0
            targets = 0
            for batch in loader:
                tick = time.perf_counter()
                optimizer.zero_grad(set_to_none=True)
                result = model(**batch, use_cache=False)
                loss = result.loss
                if not torch.isfinite(loss):
                    raise RuntimeError('Non-finite training loss')
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), cfg['training']['max_grad_norm'])
                optimizer.step()
                target_count = int((batch['labels'][:, 1:] != -100).sum())
                token_loss += float(loss.detach()) * target_count
                targets += target_count
                steps += 1
                elapsed = time.perf_counter() - tick
                record = {'epoch': epoch, 'step': steps, 'loss': float(loss.detach()),
                          'target_tokens': target_count, 'seconds': elapsed,
                          'rss_bytes': process.memory_info().rss}
                step_log.write(json.dumps(record) + '\n')
                step_log.flush()
                if steps % 25 == 0 or steps == 1:
                    print(json.dumps({'event': 'step', **record}), flush=True)
                del result, loss, batch
            seconds = time.perf_counter() - epoch_start
            total_train += seconds
            entry = {'version': version, 'epoch': epoch, 'examples': count,
                     'loss': token_loss / targets, 'target_tokens': targets,
                     'steps': len(loader), 'seconds': seconds, 'seed': cfg['training']['seed']}
            losses.append(entry)
            with (results / 'loss.csv').open('w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=entry.keys())
                writer.writeheader()
                writer.writerows(losses)
            print(json.dumps({'event': 'epoch_complete', **entry}), flush=True)
        step_log.close()
        optimizer.zero_grad(set_to_none=True)
        del optimizer
        gc.collect()
        output.mkdir(parents=True)
        model.config.use_cache = True
        model.save_pretrained(output, safe_serialization=True)
        tokenizer.save_pretrained(output)
        (output / 'training_config.yaml').write_bytes(CONFIG.read_bytes())
        metadata = {'status': 'complete', 'version': version, 'run_id': run_id,
                    'smoke': smoke, 'subset': count, 'model_name': cfg['model']['name'],
                    'base_revision': cfg['model']['revision'], 'device': 'cpu', 'dtype': 'float32',
                    'seed': cfg['training']['seed'], 'epochs_this_run': epochs,
                    'total_epochs': (parent['total_epochs'] if parent else 0) + epochs,
                    'initialize': init, 'libraries': cfg['libraries'],
                    'dataset_sha256': data_info['dataset_sha256'],
                    'selected_source_sha256': data_info['selected_source_sha256'],
                    'teacher_targets_sha256': data_info['teacher_targets_sha256'],
                    'first_id': rows[0]['id'], 'last_id': rows[-1]['id'],
                    'config_sha256': digest(CONFIG.read_bytes()),
                    'parameters': sum(p.numel() for p in model.parameters())}
        write_json(output / 'version.json', metadata)
        from training.artifacts import prepare
        prepare(output)
        # Round-trip the checkpoint with Transformers before declaring success.
        del model
        gc.collect()
        check = AutoModelForCausalLM.from_pretrained(output, local_files_only=True,
                        torch_dtype=torch.float32, attn_implementation='eager').to('cpu')
        assert sum(p.numel() for p in check.parameters()) == metadata['parameters']
        assert all(p.device.type == 'cpu' for p in check.parameters())
        del check
        summary = {**metadata, 'epochs': losses, 'steps': steps, 'training_seconds': total_train,
                   'elapsed_seconds': time.perf_counter() - started,
                   'steps_per_second': steps / total_train,
                   'examples_per_second': count * epochs / total_train,
                   'peak_sampled_rss_bytes': max(samples + [process.memory_info().rss]),
                   'process_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                   'platform': platform.platform(), 'torch_threads': torch.get_num_threads(),
                   'checkpoint_path': str(output.relative_to(ROOT)), 'checkpoint_reload_passed': True}
        write_json(results / 'summary.json', summary)
        if smoke:
            write_json(ROOT / cfg['artifacts']['results_root'] / 'smoke-latest.json', summary)
        else:
            # Full-run losses are kept separate from smoke losses.
            public_loss = ROOT / cfg['artifacts']['loss_csv']
            existing = []
            if public_loss.exists():
                with public_loss.open() as file:
                    existing = list(csv.DictReader(file))
            if any(r['version'] == version for r in existing):
                (results / 'previous-loss.csv').write_bytes(public_loss.read_bytes())
                existing = [r for r in existing if r['version'] != version]
                print(json.dumps({'event': 'prior_loss_archived',
                                  'path': str(results / 'previous-loss.csv')}), flush=True)
            with public_loss.open('w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=losses[0].keys())
                writer.writeheader()
                writer.writerows(sorted(existing + losses, key=lambda r: (r['version'], int(r['epoch']))))
        print(json.dumps({'event': 'run_complete', **summary}), flush=True)
    except BaseException as exc:
        write_json(results / 'failure.json', {'type': type(exc).__name__, 'error': str(exc),
                                             'elapsed_seconds': time.perf_counter() - started})
        raise
    finally:
        stopped.set()
        observer.join()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--version', default='v1')
    ap.add_argument('--subset', type=int)
    args = ap.parse_args()
    run(args.version, args.subset)
