"""FastAPI API; loading and inference leave the health/readiness event loop free."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field

from service.storage import download_model, model_location

SCHEMA = Path(__file__).resolve().parents[1] / 'data/schema.json'


@dataclass(frozen=True)
class Settings:
    model_uri: str
    model_version: str
    s3_endpoint: str
    max_new_tokens: int
    fault_inject: bool = False

    @classmethod
    def from_env(cls):
        uri = os.environ['MODEL_URI']
        model_location(uri)
        version = os.environ['MODEL_VERSION']
        endpoint = os.environ['S3_ENDPOINT']
        if not version or urlsplit(endpoint).scheme not in ('http', 'https'):
            raise ValueError('Invalid version or S3 endpoint')
        limit = int(os.environ['MAX_NEW_TOKENS'])
        fault = os.environ.get('FAULT_INJECT', '0')
        if not 1 <= limit <= 256 or fault not in ('0', '1'):
            raise ValueError('Invalid MAX_NEW_TOKENS or FAULT_INJECT')
        return cls(uri, version, endpoint, limit, fault == '1')


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(min_length=1, max_length=4096)


def log(event, **fields):
    print(json.dumps({'time': time.time(), 'event': event, **fields}), flush=True)


def load_runtime(settings):
    started = time.perf_counter()
    path = Path(tempfile.mkdtemp(prefix='parser-')) / 'model'
    download_model(settings, path, log)
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(42)
    torch.use_deterministic_algorithms(True)
    from student.runtime import load_model, generate_raw
    model, tokenizer = load_model(path)
    log('model_loaded', version=settings.model_version, device=str(next(model.parameters()).device),
        seconds=time.perf_counter() - started)

    def predict(text):
        return generate_raw(model, tokenizer, text, max_new_tokens=settings.max_new_tokens,
                            max_input_tokens=256)
    return predict


def create_app(settings=None, loader=load_runtime):
    state = {'settings': settings, 'predict': None, 'error': None}
    ready = threading.Event()
    inference_lock = threading.Lock()
    validator = Draft202012Validator(json.loads(SCHEMA.read_text())['json_schema'])
    hostname = socket.gethostname()

    @asynccontextmanager
    async def lifespan(app):
        state['settings'] = settings or Settings.from_env()

        def initialize():
            try:
                state['predict'] = loader(state['settings'])
                ready.set()
                log('ready', version=state['settings'].model_version, served_by=hostname)
            except Exception as error:
                state['error'] = type(error).__name__
                log('startup_failed', error_type=type(error).__name__)
        thread = threading.Thread(target=initialize, name='model-loader', daemon=True)
        thread.start()
        yield
        ready.clear()

    app = FastAPI(lifespan=lifespan)
    app.state.model_ready = ready
    app.state.runtime = state

    @app.get('/healthz')
    async def healthz():
        return {'status': 'alive'}

    @app.get('/readyz')
    async def readyz():
        return JSONResponse({'status': 'ready' if ready.is_set() else 'loading'},
                            status_code=200 if ready.is_set() else 503)

    def infer(text):
        from student.runtime import InvalidModelOutput, extract_json
        with inference_lock:
            raw = state['predict'](text)
        if state['settings'].fault_inject:
            raw = 'not json'
        try:
            _, obj = extract_json(raw)
            validator.validate(obj)
            return obj
        except (InvalidModelOutput, ValueError) as error:
            raise InvalidModelOutput('invalid_model_output') from error
        except Exception as error:
            from jsonschema.exceptions import ValidationError
            if isinstance(error, ValidationError):
                raise InvalidModelOutput('invalid_model_output') from error
            raise

    @app.post('/parse')
    async def parse(command: Command):
        if not ready.is_set():
            return JSONResponse({'error': 'model_not_ready'}, status_code=503)
        current = state['settings']
        headers = {'X-Model-Version': current.model_version, 'X-Served-By': hostname}
        from student.runtime import InvalidModelOutput
        try:
            result = await asyncio.to_thread(infer, command.text)
            return JSONResponse(result, headers=headers)
        except InvalidModelOutput:
            log('invalid_model_output', version=current.model_version, served_by=hostname)
            return JSONResponse({'error': 'invalid_model_output'}, status_code=500, headers=headers)
        except ValueError:
            return JSONResponse({'error': 'input_too_long'}, status_code=422, headers=headers)

    return app


app = create_app()
