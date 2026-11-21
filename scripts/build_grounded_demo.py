"""Explicit local-only generation/classification; resumable synthetic artefacts, no real DB.

python scripts/build_grounded_demo.py --stage generate
python scripts/build_grounded_demo.py --stage classify
Existing results are resumed, never regenerated implicitly. No model downloads.
"""
import argparse
from collections import Counter
import csv
from datetime import date, datetime, timedelta, timezone
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.engine import PROMPT_VERSION, classify_record, load_prompt
from src.analysis.evaluation import evaluate_pairs
from src.analysis.ollama_client import OllamaClient, LocalModelError
from src.analysis.schema import validate_labels
from src.analysis.simulation import (NOTICE, GENERATION_VERSION, CATEGORY_COUNTS, fingerprint,
    normalized, validate_sources, validate_scenarios, scenario_distributions, diversity_report, evaluate_simulation,
    representative_case, generation_content_issues)
from src.analysis.storage import init_analysis_db, get_history
from src.data.db import insert_record

DEMO = ROOT / 'demo'
PROMPT_FILE = ROOT / 'src/analysis/prompts' / (GENERATION_VERSION + '.txt')
SOURCE_FILE = DEMO / 'media_sources.json'
DATA_FILE = DEMO / 'grounded_scenarios.json'
LOG_FILE = DEMO / 'simulation_generation.json'
RESULT_FILE = DEMO / 'simulation_classifications.json'
SOURCE_EVENTS = ['launch_2023', 'launch_2023', 'availability_2023', 'availability_2023',
    'availability_2023', 'availability_2023', 'vision_2024', 'partnership_2024', 'partnership_2024',
    'ixray_2024', 'ixray_2024', 'ixray_2024', 'ixray_2024', 'ixray_2024', 'voice_privacy_2025',
    'privacy_response_2025', 'privacy_response_2025', 'india_2025', 'gen2_2025', 'gen2_2025',
    'gen2_2025', 'market_2025', 'market_2025', 'market_2025', 'contractor_allegations_2026',
    'contractor_response_2026', 'optical_2026', 'contractor_response_2026', 'contractor_response_2026',
    'optical_2026', 'audio_gen3_2026', 'senate_2026']
PERSONAS = ['longtime sunglasses buyer', 'first-time eyewear shopper', 'busy parent', 'student',
    'teacher', 'commuter', 'photography hobbyist', 'outdoor runner', 'office worker', 'retired shopper',
    'fashion enthusiast', 'technology enthusiast', 'privacy-conscious bystander', 'small shop owner',
    'healthcare worker off duty', 'occasional traveller', 'budget-conscious buyer', 'gift shopper',
    'early adopter', 'sceptical non-owner', 'prescription-glasses wearer', 'museum visitor',
    'live music fan', 'cafe regular', 'design enthusiast', 'software developer', 'sports fan',
    'older relative with limited tech awareness', 'accessibility-minded user', 'friend of a glasses owner',
    'person who keeps old frames', 'person considering a change of brand']
STYLES = ['plain and brief', 'conversational with a practical example', 'tentative and questioning',
    'reflective and measured', 'casual and slightly frustrated', 'wry understatement',
    'a short rhetorical question followed by an opinion', 'an everyday purchasing dilemma',
    'mild sarcasm without abusive language', 'careful distinction between companies',
    'hesitant, limited knowledge', 'direct and personal', 'weighing a trade-off',
    'a chatty observation', 'understated disappointment', 'concise enthusiasm',
    'concern for people nearby', 'a sceptical question', 'pragmatic and informal', 'two contrasting thoughts']
ASSIGNMENTS = {
    'privacy_product_criticism': 'Reject the camera/AI glasses on privacy grounds, not ordinary sunglasses. Make the stated responsibility attribution explicit.',
    'wider_brand_distrust': 'Express unease about traditional Ray-Ban eyewear, not just the gadget. For explicit spillover directly link wider-brand distrust/avoidance to smart-glasses privacy; for implicit spillover leave that connection implied.',
    'meta_responsibility_brand_protected': 'Clearly hold Meta responsible for the digital/privacy side while explicitly defending traditional Ray-Ban sunglasses. Mixed opinion: criticism of Meta, protection of Ray-Ban.',
    'positive_experience': 'Express a positive opinion and interest in buying the stated target; discuss the supplied design topic without inventing technical specifications.',
    'neutral_or_mixed': 'Show limited awareness, a genuine question or a balanced trade-off. For neutral do not take sides; for mixed include both appeal and concern. Avoid forced wider-brand rejection.'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def prepare_sources():
    """Explicit bibliographic allowlist: no article text, research labels or reviewer data."""
    original = ROOT / 'data/research_news_2023_2026/articles.csv'
    if not original.exists():
        manifest = read(SOURCE_FILE)
        validate_sources(manifest['sources'])
        if manifest.get('kind') != 'public_bibliographic_context_not_customer_data' or manifest['sha256'] != fingerprint(manifest['sources']):
            raise ValueError('Public source manifest failed provenance checks.')
        return manifest['sources']
    with original.open(encoding='utf-8-sig', newline='') as handle:
        articles = list(csv.DictReader(handle))
    import hashlib
    quality = read(ROOT / 'data/research_news_2023_2026/dataset_quality.json')
    if hashlib.sha256((ROOT / 'data/research_news_2023_2026/articles.csv').read_bytes()).hexdigest() != quality['sha256']:
        raise ValueError('Original source checksum changed; stop for verification.')
    categories = {'independent_media': 'independent_media', 'company': 'company_statements', 'official_body': 'official_regulatory'}
    if len(articles) != len(SOURCE_EVENTS):
        raise ValueError('Source-event mapping requires exactly the frozen 32 sources.')
    sources = [dict(**{key: row[key] for key in ('source_id', 'published_at', 'publisher', 'title', 'url', 'event_topic', 'evidence_type', 'verification_status')},
                    source_category=categories[row['publisher_type']], event_id=event)
               for row, event in zip(articles, SOURCE_EVENTS)]
    validate_sources(sources)
    if SOURCE_FILE.exists() and read(SOURCE_FILE)['sources'] != sources:
        raise ValueError('Existing public source manifest differs; do not silently replace it.')
    save(SOURCE_FILE, dict(kind='public_bibliographic_context_not_customer_data',
        source_sha256=quality['sha256'], verification='Existing collection verification; no fresh URL availability claim.',
        sources=sources, sha256=fingerprint(sources)))
    return sources


def make_plan(sources, events):
    by_event = {event['event_id']: event for event in events}
    tasks = []
    for category, count in CATEGORY_COUNTS.items():
        for i in range(count):
            number = len(tasks)
            source = sources[number % len(sources)]
            event = by_event[source['event_id']]
            labels = dict(sentiment='negative', target='Ray-Ban Meta', responsibility='unclear',
                          spillover='none', purchase_intent='negative', topic=['privacy'])
            if category == 'privacy_product_criticism':
                labels['responsibility'] = ('Meta', 'Ray-Ban', 'both', 'unclear')[i % 4]
                labels['topic'] = ['privacy', 'recording'] if i % 2 else ['privacy']
            elif category == 'wider_brand_distrust':
                labels.update(target='core Ray-Ban' if i % 2 else 'both',
                    responsibility=('Meta', 'Ray-Ban', 'both', 'unclear')[i % 4],
                    spillover='explicit' if i < 30 else 'implicit', purchase_intent='negative' if i < 30 else 'unclear')
            elif category == 'meta_responsibility_brand_protected':
                labels.update(sentiment='mixed', target='Meta', responsibility='Meta',
                              purchase_intent='positive' if i % 3 == 0 else 'unclear')
            elif category == 'positive_experience':
                labels.update(sentiment='positive', target=('Ray-Ban Meta', 'core Ray-Ban')[i % 2],
                              purchase_intent='positive', topic=[('fashion', 'technology', 'convenience', 'safety')[i % 4]])
            else:
                labels.update(sentiment='neutral' if i < 20 else 'mixed', target='unclear' if i % 2 else 'Ray-Ban Meta',
                              responsibility='unclear', spillover='unclear' if i % 2 else 'none', purchase_intent='unclear',
                              topic=['privacy', 'technology'] if i % 2 else ['other'])
            published = min(date(2026, 11, 19), max(date.fromisoformat(source['published_at']), date.fromisoformat(event['date'])) + timedelta(days=number % 13))
            tasks.append(dict(synthetic_id=f'SIM-{number + 1:04}', scenario_category=category,
                related_article_ids=[source['source_id']], related_event_ids=[event['event_id']],
                simulated_publication_date=published.isoformat(), simulated_publication_year=published.year,
                expected_labels=labels, persona=PERSONAS[number % len(PERSONAS)],
                writing_style=STYLES[(number * 7 + number // 20) % len(STYLES)],
                requested_length=('8-16 words', '18-30 words', '35-55 words', '25-40 words')[number % 4],
                context=dict(article_id=source['source_id'], article_date=source['published_at'],
                    article_topics=source['event_topic'], evidence_type=source['evidence_type'],
                    event_date=event['date'], event_brief=event['description'], limitation=event['limitation'])))
    return tasks


def export_csv(report):
    fields = ['synthetic_id', 'source_kind', 'is_synthetic', 'text', 'scenario_category',
              'related_article_ids', 'related_event_ids', 'simulated_publication_date', 'simulated_publication_year',
              'sentiment', 'target', 'responsibility', 'spillover', 'purchase_intent', 'topic', 'expected_labels',
              'generation_model', 'generation_model_version', 'generation_prompt_version']
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for row in report['records']:
        item = {key: row[key] for key in fields if key in row}
        item.update(row['expected_labels'])
        for key, value in item.items():
            if isinstance(value, (dict, list)):
                item[key] = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                item[key] = "'" + value
        writer.writerow(item)
    (DEMO / 'grounded_scenarios.csv').write_bytes(buffer.getvalue().encode('utf-8-sig'))


def write_findings(dataset, output):
    """Report only saved observations, separating design counts and model agreement."""
    summary = output['summary']
    generation = read(LOG_FILE)
    produced = 0
    for attempt in generation['attempts']:
        try:
            produced += len(json.loads(attempt['raw_output']).get('comments', []))
        except (ValueError, TypeError, AttributeError):
            pass
    lines = ['# Grounded synthetic demonstration: recorded results', '', '**' + NOTICE + '**', '',
        f"Final scenarios: {len(dataset['records'])}. Recorded classifications: {summary['n']}; "
        f"accepted {summary['accepted']}; rejected {summary['rejected']}; categorical-evaluable raw {summary['evaluable']}.", '',
        f"Generation audit: {produced} complete comment objects across {len(generation['attempts'])} recorded attempts; "
        f"{len(generation.get('selection_events', []))} drafts selected for pre-classification wording replacement. "
        'Development pilots are retained separately and are not part of the final dataset.', '',
        'References are scenario-design intentions, not independently validated ground truth. '
        'Generation and classification use the same local model. Agreement cannot estimate real-world accuracy, '
        'customer sentiment, historical trends or actual brand damage.', '',
        '## Designed corpus, not model findings', '', '| Scenario category | Count |', '| --- | ---: |']
    for category, n in Counter(r['scenario_category'] for r in dataset['records']).items():
        lines.append(f'| {category} | {n} |')
    lines.extend(['', '| Design field | Label | Count / total scenarios |', '| --- | --- | ---: |'])
    for field, counts in scenario_distributions(dataset['records']).items():
        for label, n in counts.items():
            lines.append(f"| {field} | {label} | {n}/{len(dataset['records'])} |")
    lines.extend(['', '## Model agreement, separate from scenario distributions', '',
        '| Field | Raw evaluable accuracy | Accepted-only accuracy |', '| --- | ---: | ---: |'])
    def percent(value):
        return 'undefined' if value is None else f'{100 * value:.1f}%'
    for field in summary['raw_metrics']['fields']:
        lines.append(f"| {field} | {percent(summary['raw_metrics']['fields'][field]['accuracy'])} (n={summary['evaluable']}) | "
                     f"{percent(summary['accepted_metrics']['fields'][field]['accuracy'])} (n={summary['accepted']}) |")
    lines.extend(['', '| Explicit-spillover basis | TP | FP | FN | TN | Precision | Recall | F1 |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |'])
    for basis in ('raw_metrics', 'accepted_metrics'):
        score = summary[basis]['explicit_spillover']
        lines.append(f"| {basis} | {score['tp']} | {score['fp']} | {score['fn']} | {score['tn']} | "
                     f"{percent(score['precision'])} | {percent(score['recall'])} | {percent(score['f1'])} |")
    lines.extend(['', 'Raw metrics include rejected outputs only when their categorical fields are evaluable. '
        'Accepted-only results are selected by safeguards. Rejections are abstentions, not `none`. '
        'Unparseable outputs are absent from raw confusion matrices and remain in the rejection count.', '',
        f"Mean recorded inference time: {summary['mean_seconds']:.2f} seconds/comment (local machine, not a portable speed claim).", '',
        'Raw evaluable explicit false positives: ' + (', '.join(summary['false_positives']) or 'none') + '.', '',
        'Raw evaluable explicit false negatives: ' + (', '.join(summary['false_negatives']) or 'none') + '.', '',
        'Rejected design-reference explicit positives: ' + (', '.join(summary['rejected_reference_positives']) or 'none') + '.', '',
        '## Actual accepted-model label counts', '', '| Field | Label | Count / accepted |', '| --- | --- | ---: |'])
    for field, counts in summary['accepted_prediction_distributions'].items():
        for label, n in counts.items():
            lines.append(f"| {field} | {label} | {n}/{summary['accepted']} |")
    lines.extend(['', '## Observed limitations of this recorded run', '',
        f"Accepted explicit-spillover predictions: {summary['accepted_prediction_distributions']['spillover'].get('explicit', 0)}. "
        'Zero accepted explicit outputs is not evidence of zero real spillover, nor does it rule out Reaction B. '
        'Intended scenario labels and accepted model labels remain separate.', '',
        'Safeguard rejection reasons:', ''])
    for reason, n in Counter(r.get('validation', r.get('parse_error', 'No evaluable response')) for r in output['results'] if r['status'] != 'success').items():
        lines.append(f'- {n}: {reason}')
    lines.extend(['', 'Generation references can disagree with the actual wording, especially target scope, '
        'responsibility and explicit versus implicit distrust. Guard acceptance also depends on exact quotations '
        'and conservative wording checks. Independent human coding is needed to disentangle reference problems, '
        'model errors and safeguard abstentions. This is a different corpus from the fixed v1/v2 benchmarks; '
        'their scores are not a paired measure of improvement or decline on these scenarios.', ''])
    lines.extend(['', '## Raw evaluable confusion matrices', '', 'Rows are design references; columns are raw model predictions.'])
    for field, data in summary['raw_metrics']['fields'].items():
        choices = list(data['confusion'])
        lines.extend(['', '### ' + field, '', '| Reference / predicted | ' + ' | '.join(choices) + ' |',
                      '| --- | ' + ' | '.join('---:' for _ in choices) + ' |'])
        for truth, counts in data['confusion'].items():
            lines.append('| ' + truth + ' | ' + ' | '.join(str(counts[c]) for c in choices) + ' |')
    lines.extend(['', '## Reactions A, B and C: illustrative cases, not empirical tests', ''])
    for hypothesis, category in [('Reaction A', 'privacy_product_criticism'), ('Reaction B', 'wider_brand_distrust'), ('Reaction C', 'meta_responsibility_brand_protected')]:
        case = representative_case(dataset['records'], category)
        if case is None:
            continue
        prediction = next(row for row in output['results'] if row['case'] == case['synthetic_id'])
        lines.extend([f"**{hypothesis}, {case['synthetic_id']} — simulated:** {case['text']}", '',
            f"Design spillover: {case['expected_labels']['spillover']}; actual raw model spillover: "
            f"{(prediction.get('parsed_output') or {}).get('spillover', 'unparseable')}; safeguard status: {prediction['status']}.", ''])
    quality = validate_scenarios(dataset, read(SOURCE_FILE)['sources'], read(DEMO / 'research_timeline.json')['events'])
    lines.extend(['## Provenance, diversity and limitations', '',
        f"Source coverage: {quality['source_coverage']}/32 existing references. Simulated year counts: {quality['years']}.", '',
        'All public IDs/URLs/dates match the existing bibliographic manifest; no fresh website-availability claim is made. '
        'Original articles and human-review events remain separate and unchanged. Only metadata topics and independently '
        'written event briefs were sent to local generation, never restricted publisher text.', '',
        'Lexical checks (not semantic or human validation):', '', '```json',
        json.dumps(diversity_report(dataset['records']), ensure_ascii=False, indent=2), '```', '',
        'Structural generation rejections and pilot selection precede classifier evaluation. They improve presentation '
        'quality without establishing reference-label validity. Some wording may depart from its planned label; '
        'responsibility/target ambiguity and safeguards can therefore reduce agreement. No references were changed '
        'after observing classifier outputs.', '',
        f"Model: {output['model']['model_name']}; digest: `{output['model']['model_version']}`; "
        f"classification prompt: `{output['prompt_version']}`; dataset fingerprint: `{output['records_sha256']}`.", '',
        'See SYNTHETIC_DEMONSTRATION.md for the full methodology and STRATEGIC_IMPLICATIONS.md for conditional recommendations.'])
    (ROOT / 'docs/GROUNDED_SIMULATION_RESULTS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def generate(model, batch_size=1):
    sources = prepare_sources()
    events = read(DEMO / 'research_timeline.json')['events']
    tasks = make_plan(sources, events)
    prompt = PROMPT_FILE.read_text(encoding='utf-8')
    client = OllamaClient(model)
    try:
        metadata = client.inspect()
        task_hash, prompt_hash = fingerprint(tasks), fingerprint(prompt)
        report = read(DATA_FILE) if DATA_FILE.exists() else dict(is_synthetic=True, notice=NOTICE, completed=False,
            created_at=datetime.now(timezone.utc).isoformat(), source_manifest_sha256=fingerprint(sources),
            timeline_sha256=fingerprint(events), plan_sha256=task_hash, generation_prompt_sha256=prompt_hash,
            generation_model=metadata, reference_basis='Scenario-design labels supplied to generator; not independently validated ground truth.',
            category_quotas=CATEGORY_COUNTS, records=[])
        log = read(LOG_FILE) if LOG_FILE.exists() else dict(is_synthetic=True, plan=tasks, attempts=[])
        if report['plan_sha256'] != task_hash or report['generation_prompt_sha256'] != prompt_hash or report['generation_model'] != metadata:
            raise ValueError('Frozen plan, prompt or local model changed; refusing mixed provenance.')
        done = {r['synthetic_id'] for r in report['records']}
        pending = [task for task in tasks if task['synthetic_id'] not in done]
        for offset in range(0, len(pending), batch_size):
            batch = pending[offset:offset + batch_size]
            success = False
            prior_attempts = sum(a['task_ids'] == [t['synthetic_id'] for t in batch] for a in log['attempts'])
            for retry in range(6 if log.get('enforce_content_checks') else 3):
                if fingerprint(PROMPT_FILE.read_text(encoding='utf-8')) != prompt_hash:
                    raise ValueError('Generation prompt changed mid-run.')
                seed = int(batch[0]['synthetic_id'].split('-')[1]) * 17 + prior_attempts + retry
                payload = dict(tasks=[dict(synthetic_id=t['synthetic_id'], category=t['scenario_category'],
                    expected_labels=t['expected_labels'], perspective=t['persona'], style=t['writing_style'],
                    length=t['requested_length'], context=t['context']['event_brief'],
                    context_limit=t['context']['limitation'], article_topics=t['context']['article_topics'],
                    simulated_date=t['simulated_publication_date'], assignment=ASSIGNMENTS[t['scenario_category']]) for t in batch],
                    avoid_repeating_recent_openings=[r['text'][:55] for r in report['records'][-5:]])
                if log.get('enforce_content_checks'):
                    payload['required_content'] = [dict(synthetic_id=t['synthetic_id'], instruction=(
                        'NEGATIVE WIDER-BRAND REACTION: express distrust/avoidance of ordinary Ray-Ban sunglasses. '
                        'Do not praise or defend traditional Ray-Ban. For explicit spillover link wider-brand distrust '
                        'to smart-glasses privacy; for implicit spillover express unease without stating that full causal rejection.'
                        if t['scenario_category'] == 'wider_brand_distrust' else
                        'META-FOCUSED RESPONSIBILITY: explicitly name Meta as responsible for the digital/privacy side. '
                        'Preserve trust in ordinary/traditional Ray-Ban sunglasses. Do not reject the traditional brand.')) for t in batch]
                schema = dict(type='object', properties=dict(comments=dict(type='array', minItems=len(batch), maxItems=len(batch),
                    items=dict(type='object', properties=dict(synthetic_id=dict(type='string', enum=[t['synthetic_id'] for t in batch]), text=dict(type='string')),
                               required=['synthetic_id', 'text'], additionalProperties=False))), required=['comments'], additionalProperties=False)
                started = time.perf_counter()
                options = dict(temperature=0.85, seed=seed, num_predict=min(1800, 400 * len(batch)))
                request_content = json.dumps(payload)
                if log.get('enforce_content_checks') and len(batch) == 1:
                    category = batch[0]['scenario_category']
                    constraint = ('Use the literal word Meta as the company the speaker holds responsible, and '
                        'the literal words traditional Ray-Ban for the eyewear they still trust.'
                        if category == 'meta_responsibility_brand_protected' else
                        'The speaker feels NEGATIVELY about traditional Ray-Ban sunglasses because of the association, '
                        'not just the smart product. Do not defend or praise traditional Ray-Ban in this reaction.')
                    request_content += '\nCrucial requirement for this ONE fictional comment: ' + constraint
                    request_content += ('\nMake this a fresh, specific reaction from the perspective of a ' + batch[0]['persona'] +
                        '. Include a concrete personal situation instead of a generic slogan. Writing style: ' + batch[0]['writing_style'] +
                        '. Avoid stock slogan wording and vary the sentence structure.')
                try:
                    response = client._call('POST', '/api/chat', dict(model=model, stream=False, format=schema,
                        messages=[dict(role='system', content=prompt), dict(role='user', content=request_content)], options=options))
                except LocalModelError as exc:
                    log['attempts'].append(dict(task_ids=[t['synthetic_id'] for t in batch], seed=seed,
                        raw_output=None, seconds=time.perf_counter() - started, status='transport_failure',
                        error=str(exc), input_payload=payload, generation_options=options, prompt_sha256=prompt_hash,
                        request_content=request_content,
                        model_version=metadata['model_version']))
                    save(LOG_FILE, log)
                    save(DATA_FILE, report)
                    raise
                raw = (response.get('message') or {}).get('content')
                attempt = dict(task_ids=[t['synthetic_id'] for t in batch], seed=seed, raw_output=raw,
                    seconds=time.perf_counter() - started, status='rejected', model_version=metadata['model_version'],
                    input_payload=payload, temperature=0.85, prompt_sha256=prompt_hash,
                    request_content=request_content,
                    generation_options=options,
                    token_counts={key: response.get(key) for key in ('prompt_eval_count', 'eval_count', 'prompt_eval_duration', 'eval_duration')})
                try:
                    if response.get('done') is not True or response.get('done_reason') not in (None, 'stop') or response.get('model') != model:
                        raise ValueError('Incomplete generation or unexpected model identity.')
                    comments = json.loads(raw)['comments']
                    if len(comments) != len(batch) or {c['synthetic_id'] for c in comments} != {t['synthetic_id'] for t in batch}:
                        raise ValueError('Generated IDs differ from requested tasks.')
                    by_id = {c['synthetic_id']: c['text'] for c in comments}
                    new = [dict(**{k: v for k, v in task.items() if k != 'context'}, text=by_id[task['synthetic_id']],
                        is_synthetic=True, source_kind='AI-generated simulation', generation_model=model,
                        generation_model_version=metadata['model_version'], generation_prompt_version=GENERATION_VERSION) for task in batch]
                    trial = dict(report, records=report['records'] + new)
                    validate_scenarios(trial, sources, events, complete=False)
                    for row in new:
                        if log.get('enforce_content_checks') and generation_content_issues(row):
                            raise ValueError('; '.join(generation_content_issues(row)))
                        if re.match(r'(?i)(sarcastic|neutral|positive|negative|mixed) (reaction|response):', row['text']):
                            raise ValueError('Artificial style label is not a customer-like reaction.')
                    report['records'].extend(new)
                    attempt['status'] = 'accepted'
                    success = True
                except (ValueError, TypeError, KeyError) as exc:
                    attempt['error'] = str(exc)
                log['attempts'].append(attempt)
                save(LOG_FILE, log)
                save(DATA_FILE, report)
                print(f'Generation {len(report["records"])}/260 batch={offset // batch_size + 1} {attempt["status"]} {attempt["seconds"]:.1f}s', flush=True)
                if success:
                    break
            if not success:
                raise ValueError('Generation exhausted bounded attempts; inspect preserved outputs before resuming.')
        report['records'].sort(key=lambda row: row['synthetic_id'])
        report['quality'] = validate_scenarios(report, sources, events)
        report['quality']['diversity'] = diversity_report(report['records'])
        report['scenario_distributions'] = scenario_distributions(report['records'])
        report['records_sha256'] = fingerprint(report['records'])
        report['completed'] = True
        save(DATA_FILE, report)
        export_csv(report)
    finally:
        client.close()


def repair_generation(model, record_ids=()):
    """Regenerate unclear scenario wording before any classifier outputs are observed."""
    if RESULT_FILE.exists():
        raise ValueError('Do not revise generated inputs after classification has started.')
    report = read(DATA_FILE)
    if report.get('completed') is not True:
        raise ValueError('Finish initial generation before the content review stage.')
    flagged = {r['synthetic_id']: generation_content_issues(r) for r in report['records'] if generation_content_issues(r)}
    known = {r['synthetic_id'] for r in report['records']}
    if not set(record_ids) <= known:
        raise ValueError('Unknown synthetic ID requested for pre-classification wording review.')
    flagged.update({key: ['manual_preclassification_wording_review'] for key in record_ids})
    if not flagged:
        print('Content review: no missing actor/core-brand wording cues.', flush=True)
        return
    archive = ROOT / f'benchmarks/grounded_generation_before_content_review_{fingerprint(report["records"])[:12]}.json'
    archive.parent.mkdir(exist_ok=True)
    if archive.exists():
        raise FileExistsError('Preserve the existing pre-review snapshot before a second content-review cycle.')
    archive.write_bytes(DATA_FILE.read_bytes())
    log = read(LOG_FILE)
    log['enforce_content_checks'] = True
    log.setdefault('selection_events', []).extend(dict(synthetic_id=r['synthetic_id'],
        previous_text_sha256=fingerprint(r['text']), reason=flagged[r['synthetic_id']],
        selected_at=datetime.now(timezone.utc).isoformat(), policy='Pre-classification wording check; design labels unchanged')
        for r in report['records'] if r['synthetic_id'] in flagged)
    report['records'] = [r for r in report['records'] if r['synthetic_id'] not in flagged]
    report['completed'] = False
    for field in ('quality', 'records_sha256', 'scenario_distributions'):
        report.pop(field, None)
    save(LOG_FILE, log)
    save(DATA_FILE, report)
    print(f'Content review: regenerating {len(flagged)} drafts; original outputs and snapshot preserved.', flush=True)
    generate(model)


def classify(model):
    report = read(DATA_FILE)
    if report.get('completed') is not True or report.get('records_sha256') != fingerprint(report['records']):
        raise ValueError('Finish and freeze generation before classifying the demonstration corpus.')
    sources = read(SOURCE_FILE)['sources']
    events = read(DEMO / 'research_timeline.json')['events']
    validate_scenarios(report, sources, events)
    prompt_hash = fingerprint(load_prompt(PROMPT_VERSION))
    client = OllamaClient(model)
    try:
        metadata = client.inspect()
    finally:
        client.close()
    output = read(RESULT_FILE) if RESULT_FILE.exists() else dict(synthetic_only=True, notice=NOTICE, completed=False,
        created_at=datetime.now(timezone.utc).isoformat(), records_sha256=fingerprint(report['records']),
        prompt_version=PROMPT_VERSION, prompt_sha256=prompt_hash, model=metadata, results=[])
    if output['records_sha256'] != fingerprint(report['records']) or output['prompt_sha256'] != prompt_hash or output['model'] != metadata:
        raise ValueError('Frozen classification inputs changed; refusing to mix runs.')
    done = {row['case'] for row in output['results']}
    with tempfile.TemporaryDirectory(prefix='rayban_synthetic_demo_') as temporary:
        database = Path(temporary) / 'synthetic.db'
        init_analysis_db(database)
        for case in report['records']:
            if case['synthetic_id'] in done:
                continue
            if fingerprint(load_prompt(PROMPT_VERSION)) != prompt_hash:
                raise ValueError('Classification prompt changed mid-run.')
            record_id = insert_record(dict(source='Imported', source_type='customer_discussion', collection_method='CSV import',
                text=case['text'], is_synthetic=True, raw_payload={'purpose': 'AI-generated simulation', 'synthetic_id': case['synthetic_id']}), db_path=database)
            started = time.perf_counter()
            result = classify_record(record_id, model, db_path=database)
            attempt = get_history(record_id, database)['attempts'][-1]
            row = dict(case=case['synthetic_id'], reference=case['expected_labels'], raw_output=attempt['raw_output'],
                status=result['status'], error=attempt['error'], seconds=time.perf_counter() - started,
                classified_at=attempt['created_at'], input_sha256=attempt['input_hash'], needs_review=result['needs_review'],
                model_version=attempt['model_version'], runtime_version=attempt['runtime_version'], label_fields_evaluable=False)
            try:
                row['parsed_output'] = json.loads(attempt['raw_output'])
                evaluate_pairs([(row['parsed_output'], row['reference'])])
                row['label_fields_evaluable'] = True
                try:
                    validate_labels(row['parsed_output'], case['text'])
                    row['validation'] = 'passed'
                except (ValueError, TypeError, KeyError) as exc:
                    row['validation'] = str(exc)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                row['parse_error'] = str(exc)
            output['results'].append(row)
            output['summary'] = evaluate_simulation(output['results'])
            save(RESULT_FILE, output)
            print(f'Classification {len(output["results"])}/260 {row["status"]} {row["seconds"]:.1f}s', flush=True)
    output['completed'] = True
    save(RESULT_FILE, output)
    write_findings(report, output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['generate', 'repair', 'classify'], required=True)
    parser.add_argument('--model', default='qwen2.5:3b')
    parser.add_argument('--batch-size', type=int, default=1)
    parser.add_argument('--repair-id', action='append', default=[], help='Explicit pre-inference wording-review ID; original outputs are preserved')
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 10:
        parser.error('Batch size must be between 1 and 10.')
    if args.stage == 'generate':
        generate(args.model, args.batch_size)
    elif args.stage == 'repair':
        repair_generation(args.model, args.repair_id)
    else:
        classify(args.model)
