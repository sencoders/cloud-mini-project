"""Generate raw CPU predictions from a verified, downloaded GitHub Release asset."""
import argparse
import json
from pathlib import Path

from ci.release import ROOT, extract_verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--version', choices=['v1', 'v2'], default='v1')
    parser.add_argument('--bad-model', action='store_true')
    parser.add_argument('--out', default='results/ci/predictions.jsonl')
    args = parser.parse_args()
    destination = ROOT / '.local/ci-model' / args.version
    verified = extract_verified(args.archive, args.version, destination)
    import torch
    torch.set_num_threads(2)
    torch.manual_seed(42)
    if args.bad_model:
        # A real untrained student, not deliberately corrupted labels/predictions.
        from huggingface_hub import snapshot_download
        destination = snapshot_download('EleutherAI/pythia-70m',
            revision='a39f36b100fe8a5377810d56c3f4789b9c53ac42',
            allow_patterns=['*.json', '*.safetensors', '*.txt'])
    from student.runtime import load_model, generate_raw
    model, tokenizer = load_model(destination)
    rows = [json.loads(line) for line in (ROOT / 'data/validation.jsonl').read_text().splitlines()]
    if len(rows) != 100 or len({r['id'] for r in rows}) != 100:
        raise ValueError('Expected all 100 unique validation IDs')
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w') as stream:
        for row in rows:
            raw = generate_raw(model, tokenizer, row['text'], max_new_tokens=128)
            stream.write(json.dumps({'id': row['id'], 'prediction': raw}) + '\n')
            stream.flush()
    verified.update({'bad_model': args.bad_model, 'examples': len(rows), 'device': 'cpu'})
    output.with_suffix('.provenance.json').write_text(json.dumps(verified, indent=2) + '\n')


if __name__ == '__main__':
    main()
