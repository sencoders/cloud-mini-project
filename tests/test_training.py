import json

import pytest
import torch

from student.runtime import InvalidModelOutput, extract_json
from training.common import digest
from training.data import CompletionCollator, command_prompt, encode_example, select_records


class CharacterTokenizer:
    eos_token_id = 0

    def __call__(self, text, **kwargs):
        return {'input_ids': [ord(c) for c in text],
                'offset_mapping': [(n, n + 1) for n in range(len(text))]}


def target():
    return ' {"intent":"weather_query","date":null,"time":null,"place":null}\n'


def test_completion_mask_preserves_teacher_text_and_eos():
    row = {'id': 'C0001', 'text': 'weather', 'teacher_raw': target()}
    encoded = encode_example(row, CharacterTokenizer(), 256)
    n = len(command_prompt(row['text']))
    assert encoded['labels'][:n] == [-100] * n
    assert encoded['labels'][n:-1] == encoded['input_ids'][n:-1]
    assert ''.join(map(chr, encoded['input_ids'][:-1])) == command_prompt('weather') + ' ' + target()
    assert encoded['input_ids'][-1] == encoded['labels'][-1] == 0


def test_no_silent_target_truncation():
    with pytest.raises(ValueError, match='refusing target truncation'):
        encode_example({'id': 'C1', 'text': 'weather', 'teacher_raw': target()}, CharacterTokenizer(), 10)


def test_padding_loss_mask_even_when_pad_equals_eos():
    examples = [{'input_ids': [4, 5, 0], 'labels': [-100, 5, 0]},
                {'input_ids': [4, 0], 'labels': [-100, 0]}]
    batch = CompletionCollator(0)(examples)
    assert batch['input_ids'].device.type == 'cpu'
    assert batch['attention_mask'].tolist() == [[1, 1, 1], [1, 1, 0]]
    assert batch['labels'].tolist() == [[-100, 5, 0], [-100, 0, -100]]
    # Genuine EOS contributes to loss while the identical padding ID does not.
    assert int((batch['labels'][:, 1:] != -100).sum()) == 3


def pool():
    return b''.join((json.dumps({'id': f'C{n:04}', 'text': f'weather {n}',
                                 'teacher_raw': target()}) + '\n').encode() for n in range(1, 1502))


def test_selection_exact_first_1500_and_smoke_prefix():
    raw = pool()
    full = select_records(raw, digest(raw) + '  train.jsonl', digest(raw), 1500)
    smoke = select_records(raw, digest(raw), digest(raw), 50)
    assert full[-1]['id'] == 'C1500'
    assert smoke == full[:50]
    assert all(r['teacher_raw'] == target() for r in full)


@pytest.mark.parametrize('fault', ['checksum', 'order', 'duplicate', 'validation_id', 'too_many'])
def test_training_refuses_data_integrity_failures(fault):
    raw = pool()
    rows = [json.loads(line) for line in raw.splitlines()]
    if fault == 'order':
        rows[0], rows[1] = rows[1], rows[0]
    elif fault == 'duplicate':
        rows[1] = rows[0]
    elif fault == 'validation_id':
        rows[-1]['id'] = 'V001'
    raw = b''.join((json.dumps(r) + '\n').encode() for r in rows)
    expected = '0' * 64 if fault == 'checksum' else digest(raw)
    with pytest.raises(ValueError):
        select_records(raw, digest(raw), expected, 1501 if fault == 'too_many' else 50)


def test_extraction_is_lossless_and_never_relabels():
    raw = target().strip()
    extracted, obj = extract_json('```json\n' + raw + '\n```')
    assert extracted == raw
    assert obj['intent'] == 'weather_query'


@pytest.mark.parametrize('raw', [
    'not json', '{', '{}', target() + target(),
    '{"bad":' + target(),
    '{"intent":"invented","date":null,"time":null,"place":null}',
    '{"intent":"alarm_set","intent":"weather_query","date":null,"time":null,"place":null}',
    '{"intent":"alarm_set","date":NaN,"time":null,"place":null}',
    '{"intent":"alarm_set","date":null,"time":null,"place":7}',
])
def test_extraction_rejects_invalid_without_fallback(raw):
    with pytest.raises(InvalidModelOutput):
        extract_json(raw)


def test_extraction_handles_braces_and_escaped_quotes_in_strings():
    raw = json.dumps({'intent': 'weather_query', 'date': None, 'time': None, 'place': 'a}b"c'})
    assert extract_json(raw)[0] == raw


def test_artifact_manifest_detects_tampering(tmp_path):
    from training.artifacts import manifest, verify_directory
    (tmp_path / 'model.safetensors').write_bytes(b'test fixture, not real weights')
    (tmp_path / 'config.json').write_text('{}')
    (tmp_path / 'model.sha256').write_bytes(manifest(tmp_path))
    verify_directory(tmp_path)
    (tmp_path / 'config.json').write_text('{"changed":true}')
    with pytest.raises(ValueError, match='checksum mismatch'):
        verify_directory(tmp_path)


def test_smoke_artifacts_cannot_be_published(tmp_path, monkeypatch):
    from training import artifacts
    monkeypatch.setattr(artifacts, 'ROOT', tmp_path)
    folder = tmp_path / 'local/v1'
    folder.mkdir(parents=True)
    (folder / 'version.json').write_text(json.dumps({'status': 'complete', 'smoke': True,
        'subset': 50, 'version': 'v1', 'model_name': 'EleutherAI/pythia-70m'}))
    with pytest.raises(ValueError, match='Only complete full-run'):
        artifacts.source_directory({'versions': {'v1': {}}, 'artifacts': {'local_root': 'local'}}, 'v1')


def test_generation_is_bounded_cpu_completion_only_and_stops_at_eos():
    from student.runtime import generate_raw

    class Tokenizer:
        eos_token_id = 0
        pad_token_id = 0

        def __call__(self, prompt, **kwargs):
            assert prompt == 'Command: weather\nJSON:'
            return {'input_ids': torch.tensor([[1, 2, 3]]), 'attention_mask': torch.ones((1, 3), dtype=torch.long)}

        def decode(self, tokens, **kwargs):
            assert kwargs == {'skip_special_tokens': False, 'clean_up_tokenization_spaces': False}
            return str(tokens)

    class Model:
        def generate(self, **kwargs):
            assert kwargs['input_ids'].device.type == 'cpu'
            assert kwargs['do_sample'] is False and kwargs['num_beams'] == 1
            assert kwargs['max_new_tokens'] == 12
            assert kwargs['eos_token_id'] == kwargs['pad_token_id'] == 0
            return torch.tensor([[1, 2, 3, 10, 11, 0, 77]])

    assert generate_raw(Model(), Tokenizer(), 'weather', max_new_tokens=12) == '[10, 11]'
    with pytest.raises(ValueError, match='Input exceeds'):
        generate_raw(Model(), Tokenizer(), 'weather', max_input_tokens=2)


def test_model_loader_refuses_tampered_checkpoint_before_loading(tmp_path):
    from training.artifacts import manifest
    from student.runtime import load_model
    (tmp_path / 'model.safetensors').write_bytes(b'test fixture')
    (tmp_path / 'model.sha256').write_bytes(manifest(tmp_path))
    (tmp_path / 'model.safetensors').write_bytes(b'tampered fixture')
    with pytest.raises(ValueError, match='Artifact checksum mismatch'):
        load_model(tmp_path)


def test_existing_full_model_is_never_overwritten(tmp_path):
    from training.train import allocate_run_paths
    output = tmp_path / 'model'
    output.mkdir()
    (output / 'weights').write_text('existing')
    results = tmp_path / 'results/v1'
    results.mkdir(parents=True)
    (results / 'evidence').write_text('original')
    with pytest.raises(FileExistsError, match='Refusing to overwrite checkpoint'):
        allocate_run_paths(output, results, False, 'stamp')
    assert (output / 'weights').read_text() == 'existing'
    assert (results / 'evidence').read_text() == 'original'


def test_fresh_clone_can_train_without_destroying_committed_evidence(tmp_path):
    from training.train import allocate_run_paths
    output = tmp_path / 'model'
    results = tmp_path / 'results/v1'
    results.mkdir(parents=True)
    (results / 'evidence').write_text('original measurement')
    allocate_run_paths(output, results, False, 'stamp')
    assert not results.exists()
    assert (tmp_path / 'results/history/v1-stamp/evidence').read_text() == 'original measurement'
