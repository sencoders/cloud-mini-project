"""Read-only model/data audit: writes only derived evidence, never trains or changes checkpoints."""
import csv
import hashlib
import json
import math
from pathlib import Path
import time

import torch
from safetensors import safe_open
from torch.utils.data import DataLoader
from transformers import AutoTokenizer
import yaml

from training.artifacts import verify_directory
from training.data import CompletionCollator, command_prompt, encode_example, select_records

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/final-audit'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def compare(left, right):
    started = time.monotonic()
    with safe_open(left, framework='pt', device='cpu') as a, safe_open(right, framework='pt', device='cpu') as b:
        common = sorted(set(a.keys()) & set(b.keys()))
        rows = []
        for name in common:
            x, y = a.get_tensor(name).reshape(-1), b.get_tensor(name).reshape(-1)
            assert x.shape == y.shape
            changed, total_abs, squared, maximum = 0, 0.0, 0.0, 0.0
            for start in range(0, x.numel(), 262144):
                xx, yy = x[start:start+262144].float(), y[start:start+262144].float()
                delta = (xx - yy).double()
                changed += int(torch.count_nonzero(delta))
                total_abs += float(delta.abs().sum())
                squared += float((delta * delta).sum())
                maximum = max(maximum, float(delta.abs().max()))
            rows.append({'tensor': name, 'elements': x.numel(), 'changed_elements': changed,
                         'max_absolute_delta': maximum, 'mean_absolute_delta': total_abs/x.numel(),
                         'squared_l2_delta': squared})
        left_only = [{'name': k, 'shape': list(a.get_tensor(k).shape),
                      'dtype': str(a.get_tensor(k).dtype)} for k in sorted(set(a.keys())-set(b.keys()))]
        right_only = sorted(set(b.keys())-set(a.keys()))
    total = sum(r['elements'] for r in rows)
    count = sum(r['changed_elements'] for r in rows)
    assert count > 0
    return {'shared_tensors': len(common), 'compared_elements': total,
            'changed_elements_after_float32_cast': count, 'changed_percent': 100*count/total,
            'changed_tensors': sum(r['changed_elements']>0 for r in rows),
            'max_absolute_delta': max(r['max_absolute_delta'] for r in rows),
            'l2_delta': math.sqrt(sum(r['squared_l2_delta'] for r in rows)),
            'left_only_state_entries': left_only, 'right_only_state_entries': right_only,
            'per_tensor': rows, 'audit_seconds': time.monotonic()-started}


def main():
    OUT.mkdir(exist_ok=True)
    torch.set_num_threads(4)
    cfg = yaml.safe_load((ROOT/'training/config.yaml').read_text())
    raw = (ROOT/cfg['data']['cache_path']).read_bytes()
    expected = cfg['data']['expected_sha256']
    rows = select_records(raw, expected, expected, 1500)
    selected_hash = hashlib.sha256(b'\n'.join(raw.splitlines()[:1500])+b'\n').hexdigest()
    target_hash = hashlib.sha256(json.dumps([r['teacher_raw'] for r in rows],ensure_ascii=False).encode()).hexdigest()
    validation = [json.loads(line) for line in (ROOT/'data/validation.jsonl').read_text().splitlines()]
    assert not ({r['text'].strip().lower() for r in rows}&{r['text'].strip().lower()for r in validation})
    tok = AutoTokenizer.from_pretrained(ROOT/cfg['model']['local_path'],local_files_only=True)
    tok.pad_token = tok.eos_token
    encoded = [encode_example(r,tok,cfg['training']['max_sequence_length']) for r in rows]
    crossing = []
    for row in rows:
        prompt = command_prompt(row['text'])
        offsets = tok(prompt+' '+row['teacher_raw'],add_special_tokens=False,return_offsets_mapping=True)['offset_mapping']
        crossing.extend([row['id'] for start,end in offsets if start < len(prompt) < end])
    examples_tokens = sum(len(r['input_ids']) for r in encoded)
    supervised = sum(sum(x!=-100 for x in r['labels'][1:]) for r in encoded)
    report = {'device':'cpu','model_name':cfg['model']['name'],'revision':cfg['model']['revision'],
        'data_sha256':expected,'selected_count':len(rows),'first_id':rows[0]['id'],'last_id':rows[-1]['id'],
        'selection_id_order':True,'training_minibatches_shuffled_deterministically':True,
        'selected_source_sha256':selected_hash,'teacher_targets_sha256':target_hash,
        'target_field':'teacher_raw','validation_id_or_text_overlap':False,
        'input_tokens_per_epoch_recomputed':examples_tokens,'supervised_tokens_per_epoch_recomputed':supervised,
        'min_sequence_tokens':min(len(r['input_ids'])for r in encoded),
        'max_sequence_tokens':max(len(r['input_ids'])for r in encoded),
        'mean_sequence_tokens':examples_tokens/len(rows),'sequence_limit':cfg['training']['max_sequence_length'],
        'truncation_policy':'raise, never truncate','truncated_examples':0,
        'prompt_completion_boundary_crossing_token_ids':crossing,
        'batch_size':cfg['training']['batch_size'],'gradient_accumulation':1,'learning_rate':cfg['training']['learning_rate'],
        'seed':cfg['training']['seed'],'optimizer':'AdamW','cpu_threads':cfg['training']['cpu_threads'],
        'runs':{}}
    assert supervised==34511 and not crossing
    for version in ('v1','v2'):
        folder=ROOT/'results/task2'/version
        summary=json.loads((folder/'summary.json').read_text())
        data=json.loads((folder/'data-verification.json').read_text())
        assert data['ids']==[r['id']for r in rows]
        assert data['selected_source_sha256']==selected_hash and data['teacher_targets_sha256']==target_hash
        assert not data['validation_used']
        steps=[json.loads(line)for line in (folder/'steps.jsonl').read_text().splitlines()]
        generator=torch.Generator(device='cpu').manual_seed(cfg['training']['seed'])
        loader=DataLoader(encoded,batch_size=cfg['training']['batch_size'],shuffle=True,generator=generator,
                          num_workers=0,collate_fn=CompletionCollator(tok.pad_token_id))
        epochs=[]; cursor=0
        for epoch in range(1,cfg['versions'][version]['epochs']+1):
            padding=0; padded=0; targets=0; weighted=0.0
            for batch in loader:
                record=steps[cursor]
                count=int((batch['labels'][:,1:]!=-100).sum())
                assert record['epoch']==epoch and record['step']==cursor+1
                assert record['target_tokens']==count
                assert torch.all(batch['labels'][batch['attention_mask']==0]==-100)
                assert torch.all(batch['labels'][:,0]==-100)
                padding+=int((batch['attention_mask']==0).sum())
                padded+=batch['input_ids'].numel();targets+=count
                weighted+=record['loss']*count;cursor+=1
            old=summary['epochs'][epoch-1]
            assert old['steps']==len(loader) and old['target_tokens']==targets
            assert math.isclose(old['loss'],weighted/targets,abs_tol=1e-12)
            epochs.append({'epoch':epoch,'recorded_optimizer_steps':len(loader),'recorded_supervised_tokens':targets,
                           'loss_recomputed_from_step_logs':weighted/targets,'logged_epoch_seconds':old['seconds'],
                           'reconstructed_padded_input_tokens':padded,'reconstructed_padding_tokens':padding})
        assert cursor==summary['steps']==len(steps)
        model_dir=ROOT/'.local/models'/version
        verify_directory(model_dir)
        assert (model_dir/'model.sha256').read_bytes()==(ROOT/'models'/version/'model.sha256').read_bytes()
        report['runs'][version]={'epochs':epochs,'optimizer_steps':cursor,
            'logged_supervised_tokens_total':sum(e['recorded_supervised_tokens']for e in epochs),
            'unpadded_input_tokens_total_recomputed':examples_tokens*len(epochs),
            'recorded_training_seconds':summary['training_seconds'],
            'recorded_function_elapsed_seconds':summary['elapsed_seconds'],
            'steps_per_second':summary['steps_per_second'],
            'mean_step_seconds_from_logs':sum(r['seconds']for r in steps)/len(steps),
            'weight_sha256':digest(model_dir/'model.safetensors'),'manifest_verified':True}
    base=ROOT/cfg['model']['local_path']/'model.safetensors'
    official=json.loads((ROOT/'results/task2/base-download.json').read_text())
    assert digest(base)==official['files']['model.safetensors']['official_lfs_sha256']
    report['official_base_sha256']=digest(base)
    report['base_to_v1']=compare(base,ROOT/'.local/models/v1/model.safetensors')
    report['v1_to_v2']=compare(ROOT/'.local/models/v1/model.safetensors',ROOT/'.local/models/v2/model.safetensors')
    assert report['base_to_v1']['compared_elements']==70426624
    assert report['v1_to_v2']['compared_elements']==70426624
    report['limitations']=['Step logs do not store individual gradient tensors or optimizer state; historical execution is supported by source ordering, logs, exact token/loss reconstruction and changed checkpoints, not independent hardware attestation.','Reconstructed input/padding totals are labelled as recomputation, not historical telemetry.']
    (OUT/'training-authenticity.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items()if k not in {'base_to_v1','v1_to_v2'}},indent=2),flush=True)
    print(json.dumps({key:{k:v for k,v in report[key].items()if k!='per_tensor'}for key in ['base_to_v1','v1_to_v2']},indent=2),flush=True)


if __name__=='__main__':
    main()
