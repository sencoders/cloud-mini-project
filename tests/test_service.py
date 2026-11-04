import hashlib
import io
import json
import threading
import time

from fastapi.testclient import TestClient
import pytest

from service.app import Settings, create_app
from service.storage import download_model, model_location, parse_manifest

VALID = '{"intent":"weather_query","date":null,"time":null,"place":"london"}'
SETTINGS = Settings('s3://models/v1/', 'v1', 'http://storage:8333', 128)


def wait_ready(client):
    for _ in range(100):
        if client.get('/readyz').status_code == 200:
            return
        time.sleep(0.01)
    raise AssertionError('Test loader did not finish')


def test_health_available_and_readiness_blocks_until_loaded():
    gate = threading.Event()

    def loader(settings):
        gate.wait(5)
        return lambda text: VALID

    with TestClient(create_app(SETTINGS, loader)) as client:
        assert client.get('/healthz').status_code == 200
        assert client.get('/readyz').status_code == 503
        assert client.post('/parse', json={'text': 'weather'}).status_code == 503
        gate.set()
        wait_ready(client)
        assert client.post('/parse', json={'text': 'weather'}).status_code == 200


def test_exact_success_schema_and_real_hostname_headers(monkeypatch):
    monkeypatch.setattr('service.app.socket.gethostname', lambda: 'parser-pod-123')
    with TestClient(create_app(SETTINGS, lambda _: lambda text: VALID)) as client:
        wait_ready(client)
        response = client.post('/parse', json={'text': 'weather in london'})
        assert response.status_code == 200 and response.json() == json.loads(VALID)
        assert set(response.json()) == {'intent', 'date', 'time', 'place'}
        assert response.headers['X-Model-Version'] == 'v1'
        assert response.headers['X-Served-By'] == 'parser-pod-123'


@pytest.mark.parametrize('raw', ['not json', '{}',
    '{"intent":"unknown","date":null,"time":null,"place":null}',
    '{"intent":"alarm_set","date":7,"time":null,"place":null}',
    '{"intent":"alarm_set","date":null,"time":null,"place":null,"extra":1}',
    '{"intent":"alarm_set","intent":"alarm_set","date":null,"time":null,"place":null}'])
def test_invalid_output_is_exact_500_without_gold_fallback(raw):
    with TestClient(create_app(SETTINGS, lambda _: lambda text: raw)) as client:
        wait_ready(client)
        response = client.post('/parse', json={'text': 'set an alarm'})
        assert response.status_code == 500
        assert response.json() == {'error': 'invalid_model_output'}


def test_fault_injection_replaces_real_generated_output():
    calls = []

    def predict(text):
        calls.append(text)
        return VALID

    config = Settings(SETTINGS.model_uri, 'v1', SETTINGS.s3_endpoint, 128, True)
    with TestClient(create_app(config, lambda _: predict)) as client:
        wait_ready(client)
        response = client.post('/parse', json={'text': 'weather'})
        assert calls == ['weather']
        assert response.status_code == 500 and response.json() == {'error': 'invalid_model_output'}


def test_failed_startup_remains_unready_with_live_process():
    def fail(_):
        raise ValueError('checksum mismatch')
    with TestClient(create_app(SETTINGS, fail)) as client:
        assert client.get('/healthz').status_code == 200
        assert client.get('/readyz').status_code == 503


@pytest.mark.parametrize('body', [{}, {'text': ''}, {'text': 3}, {'text': 'x', 'gold': VALID}])
def test_request_validation(body):
    with TestClient(create_app(SETTINGS, lambda _: lambda text: VALID)) as client:
        wait_ready(client)
        assert client.post('/parse', json=body).status_code == 422


@pytest.mark.parametrize('uri', ['file:///model', 's3://models', 's3://models/../v1', 's3://models/v1?secret=x'])
def test_invalid_model_uris(uri):
    with pytest.raises(ValueError):
        model_location(uri)


def test_settings_are_environment_only(monkeypatch):
    for key, value in {'MODEL_URI': 's3://models/v2', 'MODEL_VERSION': 'v2',
                       'S3_ENDPOINT': 'http://store:8333', 'MAX_NEW_TOKENS': '64', 'FAULT_INJECT': '1'}.items():
        monkeypatch.setenv(key, value)
    config = Settings.from_env()
    assert config.model_version == 'v2' and config.max_new_tokens == 64 and config.fault_inject
    monkeypatch.setenv('MAX_NEW_TOKENS', '10000')
    with pytest.raises(ValueError):
        Settings.from_env()


def test_missing_secret_does_not_fall_back_to_host_credentials(monkeypatch):
    from service.storage import secret_client
    monkeypatch.delenv('AWS_ACCESS_KEY_ID', raising=False)
    monkeypatch.delenv('AWS_SECRET_ACCESS_KEY', raising=False)
    with pytest.raises(KeyError):
        secret_client('http://store:8333')


class Body(io.BytesIO):
    def iter_chunks(self, chunk_size):
        while chunk := self.read(chunk_size):
            yield chunk


class MemoryS3:
    def __init__(self, files):
        self.files = files

    def get_object(self, Bucket, Key):
        assert Bucket == 'models'
        return {'Body': Body(self.files[Key.split('/')[-1]])}


def files():
    data = {'model.safetensors': b'fake weights for unit test only', 'config.json': b'{}',
            'tokenizer.json': b'{}', 'tokenizer_config.json': b'{}',
            'version.json': json.dumps({'version': 'v1', 'smoke': False, 'status': 'complete',
                                        'model_name': 'EleutherAI/pythia-70m'}).encode()}
    data['model.sha256'] = ''.join(f'{hashlib.sha256(v).hexdigest()}  {k}\n' for k, v in data.items()).encode()
    return data


def test_streaming_download_verifies_each_file_and_model_version(tmp_path):
    data = files()
    events = []
    path = download_model(SETTINGS, tmp_path / 'model', lambda e, **k: events.append(e), MemoryS3(data))
    assert (path / 'model.safetensors').read_bytes() == data['model.safetensors']
    assert events[0] == 'model_download_start' and events[-1] == 'model_download_complete'


def test_corrupt_s3_file_prevents_loading(tmp_path):
    data = files()
    data['model.safetensors'] = b'changed'
    with pytest.raises(ValueError, match='checksum mismatch'):
        download_model(SETTINGS, tmp_path / 'model', lambda *a, **k: None, MemoryS3(data))


def test_manifest_traversal_and_duplicates_fail_closed():
    with pytest.raises(ValueError):
        parse_manifest(('0' * 64 + '  ../secret\n').encode())
    data = files()['model.sha256']
    with pytest.raises(ValueError):
        parse_manifest(data + data)
