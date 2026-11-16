"""Explicit synthetic-only local case study; preserves every accepted/rejected output.

Run: python scripts/run_case_study.py --output demo/case_study_results.json
No research storage, downloads, cloud services, or prompt modifications.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.benchmark_contagion import fingerprint, summarize
from src.analysis.engine import PROMPT_VERSION, load_prompt, classify_record
from src.analysis.evaluation import evaluate_pairs
from src.analysis.ollama_client import OllamaClient
from src.analysis.schema import validate_labels
from src.analysis.storage import init_analysis_db, get_history
from src.data.db import insert_record

FIXTURE = ROOT / 'tests/fixtures/contagion_case_study_24.json'


def load_cases():
    data = json.loads(FIXTURE.read_text(encoding='utf-8'))
    if data.get('is_synthetic') is not True or len(data['examples']) != 24 or fingerprint(data['examples']) != data['sha256']:
        raise ValueError('Expected the frozen 24-case synthetic fixture.')
    if len({case['text'] for case in data['examples']}) != 24:
        raise ValueError('Case texts must be distinct.')
    for case in data['examples']:
        validate_labels(case['labels'], case['text'])
    return data


def run(output, model='qwen2.5:3b'):
    fixture = load_cases()
    output = Path(output)
    if output.exists():
        raise FileExistsError('Preserve existing results; choose a new output path.')
    prompt_hash = hashlib.sha256(load_prompt(PROMPT_VERSION).encode()).hexdigest()
    client = OllamaClient(model)
    try:
        metadata = client.inspect()
    finally:
        client.close()
    report = dict(synthetic_only=True, completed=False, model=metadata,
                  created_at=datetime.now(timezone.utc).isoformat(), prompt_version=PROMPT_VERSION,
                  prompt_sha256=prompt_hash, fixture_sha256=fixture['sha256'],
                  protocol=fixture['purpose'], results=[])
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    save()
    with tempfile.TemporaryDirectory(prefix='rayban_case_study_') as directory:
        database = Path(directory) / 'synthetic.db'
        init_analysis_db(database)
        for index, case in enumerate(fixture['examples'], 1):
            if hashlib.sha256(load_prompt(PROMPT_VERSION).encode()).hexdigest() != prompt_hash or load_cases()['sha256'] != fixture['sha256']:
                raise RuntimeError('Frozen inputs changed during inference.')
            record_id = insert_record(dict(source='Imported', source_type='customer_discussion',
                collection_method='CSV import', text=case['text'], is_synthetic=True,
                raw_payload={'purpose': 'synthetic case study', 'case': case['case']}), db_path=database)
            started = time.perf_counter()
            result = classify_record(record_id, model, db_path=database)
            seconds = time.perf_counter() - started
            attempt = get_history(record_id, database)['attempts'][-1]
            row = dict(case=case['case'], category=case['category'], text=case['text'],
                       reference=case['labels'], raw_output=attempt['raw_output'],
                       status=result['status'], error=attempt['error'], seconds=seconds,
                       model_version=attempt['model_version'], runtime_version=attempt['runtime_version'])
            try:
                row['parsed_output'] = json.loads(attempt['raw_output'])
                evaluate_pairs([(row['parsed_output'], case['labels'])])
                row['label_fields_evaluable'] = True
                try:
                    validate_labels(row['parsed_output'], case['text'])
                    row['validation'] = 'passed'
                except (ValueError, TypeError, KeyError) as exc:
                    row['validation'] = str(exc)
            except (ValueError, TypeError, KeyError) as exc:
                row['label_fields_evaluable'] = False
                row['parse_error'] = str(exc)
            report['results'].append(row)
            report['summary'] = summarize(report['results'])
            save()
            print(f'{index}/24 {row["status"]} {seconds:.2f}s', flush=True)
    report['completed'] = True
    save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', default='qwen2.5:3b')
    args = parser.parse_args()
    run(args.output, args.model)
