"""Explicitly invoked, permission-gated local classification orchestration."""
import json
from pathlib import Path

from src.analysis.ollama_client import OllamaClient, LocalModelError
from src.analysis.schema import JSON_SCHEMA, validate_labels, needs_review
from src.analysis.storage import load_eligible_record, append_attempt

PROMPT_VERSION = 'brand-contagion-2.0.0'
PROMPT_VERSIONS = ('brand-contagion-1.0.0', PROMPT_VERSION)


def load_prompt(version):
    if version not in PROMPT_VERSIONS:
        raise ValueError('Unknown classification prompt version.')
    prompt = (Path(__file__).parent / 'prompts' / f'{version}.txt').read_text(encoding='utf-8')
    return prompt if version == 'brand-contagion-1.0.0' else prompt + '\nJSON SCHEMA:\n' + json.dumps(JSON_SCHEMA)


SYSTEM_PROMPT = load_prompt(PROMPT_VERSION)


def classify_record(record_id, model, *, db_path=None, base_url='http://127.0.0.1:11434', prompt_version=None):
    version = prompt_version or PROMPT_VERSION
    prompt = load_prompt(version)
    record = load_eligible_record(record_id, db_path)
    client = OllamaClient(model, base_url=base_url)
    metadata = dict(model_name=model, model_version='unavailable', runtime_version='unavailable')
    raw = None
    try:
        metadata = client.inspect()
        # Recheck immediately before transmitting any text to local inference.
        checked = load_eligible_record(record_id, db_path)
        if checked['text'] != record['text'] or checked['_permission_id'] != record['_permission_id']:
            raise PermissionError('Input or permission changed before inference.')
        raw = client.generate(prompt, record['text'], JSON_SCHEMA)
        labels = validate_labels(raw, record['text'])
    except PermissionError:
        raise
    except (LocalModelError, ValueError, TypeError, KeyError):
        attempt = append_attempt(record, method='ollama', status='failed', labels=None,
            raw_output=raw, error='Local inference or schema/evidence validation failed.',
            metadata=metadata, prompt_version=version, needs_review=True, db_path=db_path)
        return dict(attempt_id=attempt, status='failed', needs_review=True)
    finally:
        client.close()
    attempt = append_attempt(record, method='ollama', status='success', labels=labels,
        raw_output=raw, error=None, metadata=metadata, prompt_version=version,
        needs_review=needs_review(labels), db_path=db_path)
    return dict(attempt_id=attempt, status='success', labels=labels, needs_review=needs_review(labels))


def classify_batch(record_ids, model, *, db_path=None, base_url='http://127.0.0.1:11434', prompt_version=None):
    """Sequential bounded requests. No automatic fallback or implicit DB-wide selection."""
    results = []
    for record_id in dict.fromkeys(record_ids):
        try:
            result = classify_record(record_id, model, db_path=db_path, base_url=base_url, prompt_version=prompt_version)
        except (PermissionError, ValueError) as exc:
            result = dict(status='blocked', error=str(exc))
        results.append(dict(record_id=record_id, **result))
    return results
