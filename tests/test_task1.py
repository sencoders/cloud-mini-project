import io
import json

import pytest
from botocore.exceptions import ClientError

from worker import label
from worker.clean import clean, collect, rejection
from worker.storage import get, maybe_get, put_verified, sha256


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.corrupt = False
        self.fail_key = None

    def put_object(self, Bucket, Key, Body, **kwargs):
        if Key == self.fail_key:
            raise RuntimeError('simulated storage outage')
        self.objects[Bucket, Key] = Body

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
        return {'Body': io.BytesIO(b'corrupt' if self.corrupt else self.objects[Bucket, Key])}


def row(n, text=None):
    return {'id': f'C{n:04}', 'text': text or f'command {n}'}


def record(n, text='weather in london', **updates):
    value = {'intent': 'weather_query', 'date': None, 'time': None, 'place': 'london'}
    value.update(updates)
    return {**row(n, text), 'teacher_raw': json.dumps(value)}


@pytest.mark.parametrize('size,count', [(3000, 2), (5, 2), (7, 3), (2, 5)])
def test_shard_complete_disjoint_exact_line_rule(size, count):
    rows = [row(i) for i in range(size)]
    partitions = [label.shard(rows, i, count) for i in range(count)]
    all_ids = [r['id'] for p in partitions for r in p]
    assert len(all_ids) == len(set(all_ids)) == size
    assert set(all_ids) == {r['id'] for r in rows}
    for i, part in enumerate(partitions):
        assert part == rows[i::count]


@pytest.mark.parametrize('index,count', [(-1, 2), (2, 2), (0, 0)])
def test_invalid_sharding(index, count):
    with pytest.raises(ValueError):
        label.shard([], index, count)


@pytest.mark.parametrize('raw,reason', [
    ('```json\n{}\n```', 'a_invalid_json'), ('{', 'a_invalid_json'),
    ('{"intent":NaN}', 'a_invalid_json'), ('{"intent":1,"intent":2}', 'a_invalid_json'),
    ('[]', 'b_wrong_keys'), ('null', 'b_wrong_keys'), ('{}', 'b_wrong_keys'),
    (json.dumps({'intent': 'unknown', 'date': None, 'time': None, 'place': None}), 'c_invalid_intent'),
    (json.dumps({'intent': [], 'date': None, 'time': None, 'place': None}), 'c_invalid_intent'),
])
def test_rejection_rules_abc(raw, reason):
    assert rejection({**row(1), 'teacher_raw': raw}) == reason


@pytest.mark.parametrize('slot', [12, [], {}, 'Paris', 'London'])
def test_slot_requires_null_or_exact_substring(slot):
    assert rejection(record(1, place=slot)) == 'd_invalid_slot'


def test_valid_slots_and_exact_raw_preservation():
    item = record(1)
    item['teacher_raw'] = ' \n' + item['teacher_raw'] + '\n '
    data, counts, rejected = clean([item])
    assert json.loads(data)['teacher_raw'] == item['teacher_raw']
    assert counts['kept'] == 1 and rejected == []


def test_counts_dedup_smallest_id_and_sorted_order():
    bad_a = {**record(5), 'teacher_raw': 'not json'}
    bad_b = {**record(6), 'teacher_raw': '{}'}
    records = [record(3), record(2, 'weather in london today', date='today'), record(1),
               bad_a, bad_b, record(7, intent='wrong'), record(8, place='paris')]
    data, counts, rejected = clean(records)
    assert [r['id'] for r in map(json.loads, data.splitlines())] == ['C0001', 'C0002']
    assert counts == {'input': 7, 'a_invalid_json': 1, 'b_wrong_keys': 1,
                      'c_invalid_intent': 1, 'd_invalid_slot': 1, 'duplicates': 1, 'kept': 2}
    assert len(rejected) == 5
    assert clean(list(reversed(records)))[0] == data
    assert sha256(data) == sha256(clean(records)[0])


def test_storage_verified_roundtrip_and_missing():
    s3 = MemoryS3()
    assert maybe_get(s3, 'missing') is None
    assert put_verified(s3, 'file', b'original\n') == sha256(b'original\n')
    assert get(s3, 'file') == b'original\n'
    s3.corrupt = True
    with pytest.raises(RuntimeError, match='mismatch'):
        put_verified(s3, 'file', b'original\n')


def test_storage_access_denied_is_not_missing():
    class Denied(MemoryS3):
        def get_object(self, **kwargs):
            raise ClientError({'Error': {'Code': 'AccessDenied'}}, 'GetObject')
    with pytest.raises(ClientError):
        maybe_get(Denied(), 'file')


def test_resume_after_storage_outage_no_missing_or_duplicate_ids():
    s3 = MemoryS3()
    rows = [row(i) for i in range(4)]
    calls = []

    def generate(text, prompt):
        calls.append(text)
        return '  exact teacher reply\n'

    # Crash after the checkpoint succeeded but before shard publication.
    s3.fail_key = 'teacher/shard-0.jsonl'
    with pytest.raises(RuntimeError):
        label.run(s3, rows, 'prompt', 0, 2, 'teacher', generate)
    assert calls == ['command 0']
    s3.fail_key = None
    result = label.run(s3, rows, 'prompt', 0, 2, 'teacher', generate)
    assert calls == ['command 0', 'command 2']
    assert len({r['id'] for r in result}) == 2
    assert all(r['teacher_raw'] == '  exact teacher reply\n' for r in result)
    label.run(s3, rows, 'prompt', 0, 2, 'teacher', generate)
    assert len(calls) == 2
    with pytest.raises(ValueError, match='configuration changed'):
        label.run(s3, rows, 'different prompt', 0, 2, 'teacher', generate)


def test_teacher_retry_is_recorded_once(monkeypatch):
    s3 = MemoryS3()
    attempts = []
    monkeypatch.setattr(label.time, 'sleep', lambda _: None)

    def generate(text, prompt):
        attempts.append(text)
        if len(attempts) < 3:
            raise TimeoutError('transient failure')
        return 'raw'

    assert len(label.run(s3, [row(1)], 'p', 0, 1, 't', generate)) == 1
    assert len(attempts) == 3


@pytest.mark.parametrize('mode', ['missing', 'duplicate', 'wrong_shard', 'wrong_text'])
def test_collect_rejects_incomplete_or_corrupt_shards(mode):
    s3 = MemoryS3()
    rows = [row(i) for i in range(4)]
    for i in range(2):
        part = [{**r, 'teacher_raw': '{}'} for r in rows[i::2]]
        if i == 0:
            if mode == 'missing':
                part.pop()
            elif mode == 'duplicate':
                part.append(part[0])
            elif mode == 'wrong_shard':
                part[0] = {**rows[1], 'teacher_raw': '{}'}
            else:
                part[0]['text'] = 'changed'
        put_verified(s3, f't/shard-{i}.jsonl', b''.join(label.encode(r) for r in part))
    with pytest.raises(ValueError):
        collect(s3, rows, 't', 2)


def test_pool_rejects_duplicate_ids_and_blank_lines():
    for raw in (b'{"id":"C1","text":"a"}\n\n',
                b'{"id":"C1","text":"a"}\n{"id":"C1","text":"b"}\n'):
        with pytest.raises(ValueError):
            label.load_pool(raw)


def test_ollama_request_settings_and_raw_response(monkeypatch):
    captured = {}
    raw = ' \n{"intent":"alarm_set"}\n '

    def urlopen(req, timeout):
        captured.update(json.loads(req.data))
        assert req.full_url == 'http://native-ollama:11434/api/generate'
        assert timeout == 300
        return io.BytesIO(json.dumps({'done': True, 'response': raw}).encode())

    monkeypatch.setenv('OLLAMA_URL', 'http://native-ollama:11434')
    monkeypatch.setattr(label.urllib.request, 'urlopen', urlopen)
    assert label.teacher('set an alarm', 'prompt') == raw
    assert captured['model'] == 'phi3.5:latest'
    assert captured['options']['temperature'] == 0
    assert captured['options']['seed'] == 42
    assert captured['stream'] is False
    assert captured['format'] == 'json'
