"""Explicit live local benchmark, synthetic-only, with fixed inputs and prompt hashes.

Run: python scripts/benchmark_contagion.py --output benchmarks/contagion_v2.json
No models are downloaded. Research storage and dashboard are never used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analysis.engine import PROMPT_VERSION, load_prompt, classify_record
from src.analysis.evaluation import evaluate_pairs
from src.analysis.ollama_client import OllamaClient
from src.analysis.schema import validate_labels
from src.analysis.storage import init_analysis_db, get_history
from src.data.db import insert_record

ROOT = Path(__file__).resolve().parents[1]
V1 = 'brand-contagion-1.0.0'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def load_sets():
    fixtures = ROOT / 'tests' / 'fixtures'
    regression = json.loads((fixtures / 'contagion_regression_20.json').read_text(encoding='utf-8'))
    heldout = json.loads((fixtures / 'contagion_heldout_20.json').read_text(encoding='utf-8'))
    for data in (regression, heldout):
        if data.get('is_synthetic') is not True or len(data['examples']) != 20 or fingerprint(data['examples']) != data['sha256']:
            raise ValueError('Synthetic dataset size or fingerprint mismatch.')
    texts = [case['text'] for data in (regression, heldout) for case in data['examples']]
    if len(set(texts)) != 40:
        raise ValueError('Regression and held-out texts must all be distinct.')
    return regression, heldout


def summarize(results):
    pairs = [(r['parsed_output'], r['reference']) for r in results if r.get('label_fields_evaluable')]
    accepted = [(r['parsed_output'], r['reference']) for r in results if r['status'] == 'success']
    def errors(positive):
        return [r['case'] for r in results if r.get('label_fields_evaluable') and
                ((r['parsed_output']['spillover'] == 'explicit' and r['reference']['spillover'] != 'explicit') if positive else
                 (r['parsed_output']['spillover'] != 'explicit' and r['reference']['spillover'] == 'explicit'))]
    times = [r['seconds'] for r in results]
    return dict(n=len(results), evaluable=len(pairs), accepted=len(accepted),
                raw_metrics=evaluate_pairs(pairs), accepted_metrics=evaluate_pairs(accepted),
                false_positives=errors(True), false_negatives=errors(False),
                rejected_reference_positives=[r['case'] for r in results if r['status'] != 'success' and r['reference']['spillover'] == 'explicit'],
                mean_seconds=statistics.mean(times) if times else None,
                median_seconds=statistics.median(times) if times else None,
                topic_exact_match=sum(set(p['topic']) == set(t['topic']) for p, t in pairs) / len(pairs) if pairs else None)


def run(output, model='qwen2.5:3b'):
    regression, heldout = load_sets()
    prompt_hashes = {version: hashlib.sha256(load_prompt(version).encode()).hexdigest() for version in (V1, PROMPT_VERSION)}
    client = OllamaClient(model)
    try:
        metadata = client.inspect()
    finally:
        client.close()
    report = dict(synthetic_only=True, model=metadata, prompt_sha256=prompt_hashes,
                  regression_sha256=regression['sha256'], heldout_sha256=heldout['sha256'],
                  heldout_policy='Frozen before inference; no prompt edits during this run; alternating paired v1/v2 order.',
                  results=[], summaries={})
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    tasks = [('regression', PROMPT_VERSION, case) for case in regression['examples']]
    for index, case in enumerate(heldout['examples']):
        order = (V1, PROMPT_VERSION) if index % 2 == 0 else (PROMPT_VERSION, V1)
        tasks.extend(('heldout', version, case) for version in order)
    with tempfile.TemporaryDirectory(prefix='rayban_prompt_benchmark_') as directory:
        database = Path(directory) / 'synthetic.db'
        init_analysis_db(database)
        for index, (dataset, version, case) in enumerate(tasks, 1):
            if any(hashlib.sha256(load_prompt(v).encode()).hexdigest() != h for v, h in prompt_hashes.items()):
                raise RuntimeError('Prompt changed after freezing; benchmark stopped.')
            record_id = insert_record(dict(source='Imported', source_type='customer_discussion',
                collection_method='CSV import', text=case['text'], is_synthetic=True,
                raw_payload={'purpose': 'synthetic prompt benchmark', 'case': case['case']}), db_path=database)
            started = time.perf_counter()
            result = classify_record(record_id, model, db_path=database, prompt_version=version)
            seconds = time.perf_counter() - started
            attempt = get_history(record_id, database)['attempts'][-1]
            row = dict(dataset=dataset, prompt_version=version, case=case['case'], text=case['text'],
                       reference=case['labels'], raw_output=attempt['raw_output'], status=result['status'],
                       model_version=attempt['model_version'], runtime_version=attempt['runtime_version'], seconds=seconds)
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
            report['summaries'][dataset + ':' + version] = summarize([r for r in report['results'] if r['dataset'] == dataset and r['prompt_version'] == version])
            save()
            # Do not expose held-out errors for tuning while the benchmark runs.
            print(json.dumps(dict(progress=f'{index}/{len(tasks)}', dataset=dataset, prompt=version,
                                  status=result['status'], seconds=round(seconds, 2))), flush=True)
    report['completed'] = True
    save()
    print('BENCHMARK_COMPLETE', str(output.resolve()), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', default='qwen2.5:3b')
    args = parser.parse_args()
    run(args.output, args.model)
