"""Shared CPU inference runtime for evaluation and the future inference service."""
import json
from pathlib import Path

from worker.clean import INTENTS, KEYS, reject_constant, strict_object


class InvalidModelOutput(ValueError):
    pass


def extract_json(raw):
    """Extract one balanced JSON object losslessly; never repair or guess values.

    At most one object is permitted. Prefix/suffix prose or a code fence may be
    removed, but the selected substring is retained exactly. Multiple objects,
    duplicate keys, malformed JSON or an invalid schema fail closed.
    """
    start = raw.find('{')
    if start < 0:
        raise InvalidModelOutput('No JSON object')
    depth = 0
    in_string = False
    escaped = False
    end = None
    for index in range(start, len(raw)):
        char = raw[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None or any(c in raw[end:] for c in '{}'):
        raise InvalidModelOutput('Incomplete or multiple JSON objects')
    text = raw[start:end]
    try:
        obj = json.loads(text, object_pairs_hook=strict_object, parse_constant=reject_constant)
    except ValueError as error:
        raise InvalidModelOutput('Malformed JSON object') from error
    if not isinstance(obj, dict) or set(obj) != KEYS:
        raise InvalidModelOutput('Expected exactly four schema keys')
    if not isinstance(obj['intent'], str) or obj['intent'] not in INTENTS:
        raise InvalidModelOutput('Invalid intent')
    if any(obj[k] is not None and not isinstance(obj[k], str) for k in ('date', 'time', 'place')):
        raise InvalidModelOutput('Invalid slot type')
    return text, obj


def load_model(path):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    path = Path(path)
    if (path / 'model.sha256').is_file():
        from training.artifacts import verify_directory
        verify_directory(path)
    tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
    tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(str(path), local_files_only=True,
                                                torch_dtype=torch.float32,
                                                attn_implementation='eager')
    model.to('cpu')
    model.eval()
    if any(p.device.type != 'cpu' for p in model.parameters()):
        raise RuntimeError('CPU-only execution required')
    return model, tokenizer


def generate_raw(model, tokenizer, text, max_new_tokens=128, max_input_tokens=256):
    import torch
    from training.data import command_prompt
    prompt = command_prompt(text)
    inputs = tokenizer(prompt, return_tensors='pt', add_special_tokens=False)
    if inputs['input_ids'].shape[1] > max_input_tokens:
        raise ValueError('Input exceeds configured token bound')
    inputs = {k: v.to('cpu') for k, v in inputs.items()}
    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False,
                                num_beams=1, use_cache=True,
                                eos_token_id=tokenizer.eos_token_id,
                                pad_token_id=tokenizer.pad_token_id)
    completion = output[0, inputs['input_ids'].shape[1]:].tolist()
    # EOS is a control token, not a teacher JSON character. Remove only EOS and
    # anything after it; do not strip whitespace, prose or other generated tokens.
    if tokenizer.eos_token_id in completion:
        completion = completion[:completion.index(tokenizer.eos_token_id)]
    return tokenizer.decode(completion, skip_special_tokens=False,
                            clean_up_tokenization_spaces=False)


def parse_command(model, tokenizer, text, **kwargs):
    raw = generate_raw(model, tokenizer, text, **kwargs)
    extracted, obj = extract_json(raw)
    return obj
