"""Uncached dashboard adapters and small-sample-aware calculations."""
import copy
import html
import json
from pathlib import Path
import re

import pandas as pd

from src.analysis.storage import load_eligible_record, research_predictions
from src.data.db import get_connection, get_record_by_id

MIN_SAMPLE = 20  # Display convention, not a statistical significance threshold.


def approved_discussions(db_path=None):
    conn = get_connection(db_path)
    try:
        ids = [row[0] for row in conn.execute("SELECT record_id FROM records WHERE source_type='customer_discussion' AND status='valid' AND is_synthetic=0 ORDER BY published_at, record_id")]
    finally:
        conn.close()
    records = []
    for record_id in ids:
        try:
            records.append(load_eligible_record(record_id, db_path))
        except (PermissionError, ValueError):
            continue
    return records


def classified_discussions(db_path=None):
    rows = []
    for attempt in research_predictions(db_path):
        record = get_record_by_id(attempt['record_id'], db_path)
        rows.append({**attempt, 'text': record['text'], 'source': record['source'],
                     'url': record['canonical_url'] or record['original_url'],
                     'published_at': record['published_at'], 'demo': False})
    return rows


def demo_discussions():
    """Existing declared-synthetic fixtures only. No SQLite insertions or fake dates."""
    path = Path(__file__).resolve().parents[2] / 'tests' / 'fixtures' / 'synthetic_contagion.json'
    fixture = json.loads(path.read_text(encoding='utf-8'))
    if fixture.get('is_synthetic') is not True:
        raise ValueError('Demonstration requires explicitly synthetic fixtures.')
    return [dict(record_id=f"demo:{case['case']}", attempt_id=f"demo:{case['case']}",
                 text=case['text'], source='Synthetic fixture', url=None, published_at=None,
                 prediction=copy.deepcopy(case['labels']), human_labels=None, review_id=None,
                 model_name='Curated fixture reference (not AI)', model_version='fixture-v1',
                 prompt_version='not-applicable', needs_review=True, demo=True)
            for case in fixture['examples']]


def filter_discussions(rows, *, search='', sentiments=(), topics=(), targets=(), spillovers=(), review_only=False):
    result = []
    for row in rows:
        label = row['active_labels']
        if search and search.casefold() not in row['text'].casefold():
            continue
        if sentiments and label['sentiment'] not in sentiments:
            continue
        if topics and not set(topics).intersection(label['topic']):
            continue
        if targets and label['target'] not in targets:
            continue
        if spillovers and label['spillover'] not in spillovers:
            continue
        if review_only and (row['human_labels'] is not None or not row['needs_review']):
            continue
        result.append(row)
    return result


def select_label_basis(rows, basis='AI predictions'):
    selected = []
    for row in rows:
        if basis == 'Human-reviewed labels' and row['human_labels'] is None:
            continue
        selected.append({**row, 'active_labels': copy.deepcopy(row['human_labels'] if basis == 'Human-reviewed labels' else row['prediction'])})
    return selected


def spillover_rate(rows, minimum=MIN_SAMPLE):
    """Numerator is explicitly restricted to the same denominator cohort."""
    cohort = [row for row in rows if row['active_labels']['sentiment'] == 'negative'
              and 'privacy' in row['active_labels']['topic']]
    explicit = sum(row['active_labels']['spillover'] == 'explicit' for row in cohort)
    denominator = len(cohort)
    return dict(explicit=explicit, denominator=denominator,
                percent=100 * explicit / denominator if denominator >= minimum and denominator else None)


def breakdown(rows, field):
    values = [row['active_labels'][field] for row in rows]
    return pd.Series(values, dtype='str').value_counts().rename_axis(field).reset_index(name='Records')


def sentiment_comparison(rows):
    # 'both' has multiple targets but no separate target-level sentiment labels.
    values = [dict(target=row['active_labels']['target'], sentiment=row['active_labels']['sentiment'])
              for row in rows if row['active_labels']['target'] in ('Ray-Ban Meta', 'core Ray-Ban')]
    if not values:
        return pd.DataFrame(columns=['target', 'sentiment', 'Records'])
    return pd.DataFrame(values).groupby(['target', 'sentiment']).size().reset_index(name='Records')


def spillover_trends(rows):
    values = []
    for row in rows:
        timestamp = pd.to_datetime(row.get('published_at'), utc=True, errors='coerce')
        if pd.isna(timestamp):
            continue
        values.append(dict(year=str(timestamp.year), source=row['source'], spillover=row['active_labels']['spillover']))
    if not values:
        return pd.DataFrame(columns=['year', 'source', 'spillover', 'Records'])
    return pd.DataFrame(values).groupby(['year', 'source', 'spillover']).size().reset_index(name='Records')


def highlighted_evidence(text, quotes):
    """Escape all source text; only our own mark elements become HTML."""
    quotes = sorted({q for q in quotes if q and q in text}, key=len, reverse=True)
    if not quotes:
        return html.escape(text)
    pattern = '(' + '|'.join(re.escape(q) for q in quotes) + ')'
    return ''.join(f'<mark>{html.escape(part)}</mark>' if index % 2 else html.escape(part)
                   for index, part in enumerate(re.split(pattern, text)))
