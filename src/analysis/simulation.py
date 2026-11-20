"""Offline synthetic artefact contract and descriptive evaluation; no research writes."""
from collections import Counter
import copy
from datetime import date
import hashlib
import json
import re
from urllib.parse import urlsplit

from src.analysis.evaluation import evaluate_pairs
from src.analysis.schema import LABELS, TOPICS

NOTICE = 'AI-generated customer scenarios — illustrative, not empirical customer sentiment.'
GENERATION_VERSION = 'grounded-reactions-1.0.0'
CATEGORY_COUNTS = {'privacy_product_criticism': 60, 'wider_brand_distrust': 60,
                   'meta_responsibility_brand_protected': 60, 'positive_experience': 40,
                   'neutral_or_mixed': 40}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def normalized(text):
    return ' '.join(re.findall(r'\w+', text.casefold()))


def validate_sources(sources):
    if len(sources) != 32 or len({s['source_id'] for s in sources}) != 32:
        raise ValueError('Expected 32 distinct bibliographic source references.')
    if len({s['url'] for s in sources}) != 32:
        raise ValueError('Source URLs must be unique.')
    allowed = {'source_id', 'published_at', 'publisher', 'title', 'url', 'event_topic',
               'evidence_type', 'source_category', 'event_id', 'verification_status'}
    for source in sources:
        if set(source) != allowed:
            raise ValueError('Only allowlisted bibliographic metadata may enter public sources.')
        url = urlsplit(source['url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Expected an original HTTPS source URL.')
        if not 2023 <= date.fromisoformat(source['published_at']).year <= 2026:
            raise ValueError('Source date is outside the study period.')


def validate_scenarios(report, sources, events, *, complete=True):
    if report.get('is_synthetic') is not True or report.get('notice') != NOTICE:
        raise ValueError('Synthetic provenance and visible notice are mandatory.')
    validate_sources(sources)
    if report.get('source_manifest_sha256') != fingerprint(sources):
        raise ValueError('Source manifest fingerprint mismatch.')
    by_source = {s['source_id']: s for s in sources}
    by_event = {e['event_id']: e for e in events}
    seen_ids, seen_text, categories = set(), set(), Counter()
    for row in report['records']:
        if row.get('is_synthetic') is not True or row.get('source_kind') != 'AI-generated simulation':
            raise ValueError('Every comment must remain explicitly synthetic.')
        if row['synthetic_id'] in seen_ids or normalized(row['text']) in seen_text:
            raise ValueError('Duplicate synthetic ID or normalized text.')
        seen_ids.add(row['synthetic_id'])
        seen_text.add(normalized(row['text']))
        if not row['synthetic_id'].startswith('SIM-') or not 6 <= len(row['text'].split()) <= 120:
            raise ValueError('Invalid synthetic ID or comment length.')
        if re.search(r'https?://|www\.|(?<!\w)@[\w]+', row['text']):
            raise ValueError('No fabricated comment URLs or handles.')
        if row['scenario_category'] not in CATEGORY_COUNTS:
            raise ValueError('Unknown designed scenario category.')
        categories[row['scenario_category']] += 1
        if not row['related_article_ids'] or not row['related_event_ids']:
            raise ValueError('Every comment needs real source and event links.')
        publication = date.fromisoformat(row['simulated_publication_date'])
        if not 2023 <= publication.year <= 2026 or publication.year != row['simulated_publication_year']:
            raise ValueError('Invalid simulated publication year.')
        if publication > date(2026, 11, 19):
            raise ValueError('Simulated date exceeds this frozen demonstration cutoff.')
        if any(publication < date.fromisoformat(by_source[key]['published_at']) for key in row['related_article_ids']):
            raise ValueError('Simulated date predates a linked article.')
        if any(publication < date.fromisoformat(by_event[key]['date']) for key in row['related_event_ids']):
            raise ValueError('Simulated date predates a linked event.')
        labels = row['expected_labels']
        if set(labels) != {*LABELS, 'topic'}:
            raise ValueError('Expected design labels are incomplete.')
        if any(labels[key] not in values for key, values in LABELS.items()):
            raise ValueError('Unknown scenario reference label.')
        if not labels['topic'] or any(topic not in TOPICS for topic in labels['topic']):
            raise ValueError('Unknown scenario topic.')
        if row['generation_prompt_version'] != GENERATION_VERSION or not row['generation_model_version']:
            raise ValueError('Missing generation provenance.')
    if complete and dict(categories) != CATEGORY_COUNTS:
        raise ValueError('Complete demonstration must match the disclosed design quotas.')
    return dict(n=len(seen_ids), unique_normalized_texts=len(seen_text), categories=dict(categories),
                source_coverage=len({s for r in report['records'] for s in r['related_article_ids']}),
                years=dict(Counter(str(r['simulated_publication_year']) for r in report['records'])))


def scenario_distributions(records, *, label_key='expected_labels'):
    return {field: dict(Counter(row[label_key][field] for row in records)) for field in LABELS}


def display_basis(records, results=None):
    """Detached views; prediction mode omits rejections rather than filling with references."""
    if results is None:
        return [dict(row, active_labels=copy.deepcopy(row['expected_labels'])) for row in records]
    accepted = {r['case']: r['parsed_output'] for r in results if r['status'] == 'success'}
    return [dict(row, active_labels=copy.deepcopy(accepted[row['synthetic_id']])) for row in records if row['synthetic_id'] in accepted]


def representative_case(records, category):
    """Choose an illustrative text, not a random sample or a model-correctness selection."""
    candidates = [r for r in records if r['scenario_category'] == category]
    if category == 'meta_responsibility_brand_protected':
        direct = [r for r in candidates if 'meta' in r['text'].lower() and 'ray-ban' in r['text'].lower()
                  and any(word in r['text'].lower() for word in ('traditional', 'ordinary', 'regular', 'classic'))]
        candidates = direct or candidates
    return candidates[0] if candidates else None


def generation_content_issues(row):
    """Presentation eligibility only; lexical cues are not semantic validation labels."""
    text = row['text'].lower()
    core = re.search(r'traditional|ordinary|regular|classic|whole brand|entire brand|wider brand|sunglasses', text)
    if row['scenario_category'] == 'wider_brand_distrust' and not core:
        return ['traditional_brand_boundary_not_explicit_in_wording']
    if row['scenario_category'] == 'meta_responsibility_brand_protected' and (
            'meta' not in text or not re.search(r'ray[ -]?ban', text) or not core):
        return ['named_Meta_and_traditional_Ray_Ban_boundary_needed']
    return []


def diversity_report(records):
    tokens = [normalized(row['text']).split() for row in records]
    lengths = [len(words) for words in tokens]
    openings = Counter(' '.join(words[:4]) for words in tokens)
    trigrams = [{tuple(words[i:i + 3]) for i in range(len(words) - 2)} for words in tokens]
    similar = []
    for i, left in enumerate(trigrams):
        for j in range(i):
            right = trigrams[j]
            score = len(left & right) / len(left | right) if left | right else 0
            if score >= 0.6:
                similar.append(dict(left=records[j]['synthetic_id'], right=records[i]['synthetic_id'], trigram_jaccard=score))
    return dict(min_words=min(lengths) if lengths else None, max_words=max(lengths) if lengths else None,
                mean_words=sum(lengths) / len(lengths) if lengths else None,
                unique_four_word_openings=len(openings), repeated_openings={key: n for key, n in openings.items() if n > 1},
                high_similarity_pairs=similar,
                limitation='Heuristic lexical checks do not establish naturalness, representativeness or semantic reference-label validity.')


def filter_scenarios(records, *, years=(), sentiments=(), responsibilities=(), spillovers=(), label_key='expected_labels'):
    return [row for row in records if
            (not years or row['simulated_publication_year'] in years) and
            (not sentiments or row[label_key]['sentiment'] in sentiments) and
            (not responsibilities or row[label_key]['responsibility'] in responsibilities) and
            (not spillovers or row[label_key]['spillover'] in spillovers)]


def evaluate_simulation(results):
    """Raw evaluable vs fully accepted outputs; rejections remain abstentions."""
    raw = [(r['parsed_output'], r['reference']) for r in results if r.get('label_fields_evaluable')]
    accepted = [(r['parsed_output'], r['reference']) for r in results if r['status'] == 'success']
    return dict(n=len(results), evaluable=len(raw), accepted=len(accepted), rejected=len(results) - len(accepted),
                raw_metrics=evaluate_pairs(raw), accepted_metrics=evaluate_pairs(accepted),
                raw_prediction_distributions={field: dict(Counter(prediction[field] for prediction, _ in raw)) for field in LABELS},
                accepted_prediction_distributions={field: dict(Counter(prediction[field] for prediction, _ in accepted)) for field in LABELS},
                false_positives=[r['case'] for r in results if r.get('label_fields_evaluable') and
                                r['parsed_output']['spillover'] == 'explicit' and r['reference']['spillover'] != 'explicit'],
                false_negatives=[r['case'] for r in results if r.get('label_fields_evaluable') and
                                r['parsed_output']['spillover'] != 'explicit' and r['reference']['spillover'] == 'explicit'],
                rejected_reference_positives=[r['case'] for r in results if r['status'] != 'success' and r['reference']['spillover'] == 'explicit'],
                mean_seconds=sum(r['seconds'] for r in results) / len(results) if results else None)
