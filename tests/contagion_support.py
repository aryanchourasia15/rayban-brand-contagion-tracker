"""Deterministic fixture adapter, intentionally outside production modules."""
import copy
import json
from pathlib import Path

from src.analysis.schema import validate_labels, needs_review
from src.analysis.storage import load_eligible_record, append_attempt


def examples():
    return json.loads((Path(__file__).parent / 'fixtures' / 'synthetic_contagion.json').read_text(encoding='utf-8'))['examples']


def classify_synthetic_fixture(record_id, db_path):
    record = load_eligible_record(record_id, db_path)
    if not record['is_synthetic']:
        raise ValueError('Deterministic fixture labels are synthetic-only.')
    case = next((case for case in examples() if case['text'] == record['text']), None)
    if case is None:
        raise ValueError('No fixture for this synthetic input; no heuristic guessing.')
    labels = validate_labels(copy.deepcopy(case['labels']), record['text'])
    return append_attempt(record, method='rule_based_test', status='success', labels=labels,
        raw_output=json.dumps(labels), error=None,
        metadata=dict(model_name='synthetic-fixture-rules', model_version='1', runtime_version='test-only'),
        prompt_version='synthetic-fixture-1', needs_review=needs_review(labels), db_path=db_path)
