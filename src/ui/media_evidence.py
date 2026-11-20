"""Separate, offline media coding and review tables. No customer metrics or inference."""
import copy
import csv
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / 'data/research_news_2023_2026'
CATEGORIES = ('independent_media', 'company_statements', 'official_regulatory')
CATEGORY_MAP = dict(independent_media='independent_media', company='company_statements',
                    official_body='official_regulatory')
CHOICES = dict(source_category=CATEGORIES, privacy_related=('yes', 'no', 'unclear'),
               ray_ban_mentioned=('yes', 'no'), meta_mentioned=('yes', 'no'),
               responsibility_attributed=('Meta', 'Ray-Ban', 'both', 'unclear'),
               wider_brand_association=('explicit', 'implicit', 'none', 'unclear'))
REVIEW_FIELDS = ['review_event_id', 'record_id', 'source_fingerprint', 'reviewed_at', 'reviewer_code',
                 'reviewer_decision', *CHOICES, 'supporting_evidence', 'reviewer_notes']


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def prepare_rows(articles, quality):
    """Keep original coding verbatim and expose reviewable proposals, never human labels."""
    quality_rows = {row['row_number']: row for row in quality['rows']}
    rows, seen_ids, seen_urls = [], set(), set()
    for index, original in enumerate(articles, 1):
        if original['source'] != 'News' or original['source_type'] != 'media':
            raise ValueError('Media evidence cannot contain customer discussions.')
        if original['source_id'] in seen_ids or original['url'] in seen_urls:
            raise ValueError('Duplicate media ID or URL.')
        seen_ids.add(original['source_id'])
        seen_urls.add(original['url'])
        raw = original['responsibility_explicitly_attributed']
        flags = list(quality_rows[index]['issues'])
        if raw.startswith('external_developers'):
            flags.append('external_actor_is_not_Meta_or_Ray_Ban')
        if 'contractor_Sama' in raw:
            flags.append('Meta_and_Sama_is_not_Meta_and_Ray_Ban')
        if original['publisher_type'] == 'official_body':
            flags.append('inquiry_target_is_not_established_liability')
        responsibility = 'Meta' if raw.startswith('Meta_') else 'unclear'
        evidence = original['association_evidence']
        if 'contract_termination' in raw:
            responsibility = 'unclear'
            flags.append('commercial_action_is_not_privacy_harm_attribution')
            evidence += ' Contract termination is not proof of responsibility for privacy harm.'
        wider = 'none'
        direction = 'no_separate_traditional_brand_reference_identified'
        if original['publisher'] == 'Stuff':
            wider, direction = 'explicit', 'positive_traditional_brand_comparison'
            evidence = ('A direct comparison favours traditional eyewear: "the original Ray-Bans are still the best." '
                        'This supports a brand distinction, not negative wider-brand spillover.')
            flags.append('direct_brand_reference_does_not_mean_adverse_spillover')
        elif original['publisher'] == 'WIRED':
            wider, direction = 'explicit', 'traditional_style_continuity'
            evidence = ('The conclusion says the product benefits from "the classic Ray-Ban approach to style" '
                        'while criticising its smart functions. This is styling context, not measured brand damage.')
            flags.append('style_reference_does_not_mean_adverse_spillover')
        elif original['wider_brand_association'] == 'yes':
            wider = 'unclear'
            flags.append('unverified_wider_brand_candidate')
        row = dict(record_id=original['source_id'], published_at=original['published_at'],
                   publisher=original['publisher'], title=original['title'], original_url=original['url'],
                   source_category=CATEGORY_MAP[original['publisher_type']],
                   privacy_related=original['privacy_related'], ray_ban_mentioned=original['mentions_ray_ban'],
                   meta_mentioned=original['mentions_meta'], responsibility_attributed=responsibility,
                   wider_brand_association=wider, association_direction=direction,
                   supporting_evidence=evidence, evidence_locator=original['evidence_locator'],
                   evidence_kind='short_source_quote_and_paraphrase' if wider == 'explicit' else 'original_paraphrase_not_verbatim_source_text',
                   source_check='assistant_passage_checked_not_human_validated' if wider == 'explicit' else 'previous_source_verification_not_fresh_human_coding',
                   ambiguity_flags=';'.join(flags), reviewer_decision='', review_status='pending_human_review',
                   reviewer_code='', reviewed_at='', reviewer_notes='', latest_review_event_id='',
                   original_coding_json=json.dumps(original, ensure_ascii=False, sort_keys=True),
                   source_fingerprint=hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest())
        for field, choices in CHOICES.items():
            if row[field] not in choices:
                raise ValueError(f'Invalid proposed media {field}.')
            row['reviewed_' + field] = ''
        row['reviewed_supporting_evidence'] = ''
        rows.append(row)
    return rows


def apply_review_events(rows, events):
    """Replay a supplied append-only ledger without changing original proposals or events.

    Reviewer identity/actual human participation must be verified by the study team;
    metadata strings alone cannot establish that verification. No events are invented.
    """
    result = copy.deepcopy(rows)
    by_id = {row['record_id']: row for row in result}
    seen = set()
    for event in events:
        if not all(isinstance(event.get(field), str) and event[field].strip() for field in REVIEW_FIELDS):
            raise ValueError('A review requires all labels, evidence, reviewer, date, decision and notes.')
        if event['review_event_id'] in seen or event['record_id'] not in by_id:
            raise ValueError('Duplicate review event or unknown media record.')
        seen.add(event['review_event_id'])
        row = by_id[event['record_id']]
        if event['source_fingerprint'] != row['source_fingerprint']:
            raise ValueError('Review refers to changed source metadata/coding.')
        timestamp = datetime.fromisoformat(event['reviewed_at'].replace('Z', '+00:00'))
        if timestamp.utcoffset() is None:
            raise ValueError('Review timestamps need an explicit timezone.')
        if row['reviewed_at'] and timestamp < datetime.fromisoformat(row['reviewed_at'].replace('Z', '+00:00')):
            raise ValueError('Append reviews in chronological order for each record.')
        if event['reviewer_decision'] not in ('confirm', 'correct', 'exclude', 'uncertain'):
            raise ValueError('Decision must be confirm, correct, exclude or uncertain.')
        for field, choices in CHOICES.items():
            if event[field] not in choices:
                raise ValueError(f'Invalid reviewed media {field}.')
            if event['reviewer_decision'] == 'confirm' and event[field] != row[field]:
                raise ValueError('Use correct when reviewed labels differ from the proposal.')
            row['reviewed_' + field] = event[field]
        for field in ('reviewer_decision', 'reviewer_code', 'reviewed_at', 'reviewer_notes'):
            row[field] = event[field]
        row['reviewed_supporting_evidence'] = event['supporting_evidence']
        row['latest_review_event_id'] = event['review_event_id']
        row['review_status'] = {'exclude': 'excluded_by_reviewer', 'uncertain': 'uncertain_pending_review'}.get(
            event['reviewer_decision'], 'human_review_recorded')
    return result


def review_progress(rows):
    """Resolved coverage; uncertainty remains pending, and corrections are not inter-rater scores."""
    resolved = {'human_review_recorded', 'excluded_by_reviewer'}
    reviewed = sum(row['review_status'] in resolved for row in rows)
    return dict(total=len(rows), reviewed=reviewed, pending=len(rows) - reviewed,
                uncertain=sum(row['review_status'] == 'uncertain_pending_review' for row in rows),
                flagged=sum(row['review_status'] == 'uncertain_pending_review' or
                            (bool(row['ambiguity_flags']) and row['review_status'] not in resolved) for row in rows),
                disagreements=sum(row['review_status'] == 'excluded_by_reviewer' or
                                  (row['review_status'] == 'human_review_recorded' and
                                   any(row['reviewed_' + field] != row[field] for field in CHOICES)) for row in rows))


def load_review_queue(rows, directory=None):
    """Use the existing template order and verify it still refers to these source records."""
    directory = Path(directory) if directory is not None else DATA_DIR
    template = read_csv(directory / 'human_review_template.csv')
    by_id = {row['record_id']: row for row in rows}
    if len(template) != len(rows) or {row['record_id'] for row in template} != set(by_id):
        raise ValueError('The human review template must contain each source record exactly once.')
    for item in template:
        row = by_id[item['record_id']]
        if item['source_fingerprint'] != row['source_fingerprint'] or json.loads(item['proposal_snapshot_json']) != {
                field: row[field] for field in CHOICES}:
            raise ValueError('The review template no longer matches the preserved proposals.')
        if any(item[field] != row[target] for field, target in (
                ('publication_date', 'published_at'), ('publisher', 'publisher'), ('original_url', 'original_url'))):
            raise ValueError('The review template source metadata changed.')
    return [by_id[item['record_id']] for item in template]


class ReviewConflictError(ValueError):
    """Another reviewer saved a new decision after this form was opened."""


@contextmanager
def _ledger_lock(directory):
    """OS-managed lock, automatically released on process exit; no extra dependency."""
    with (directory / '.media_review_events.lock').open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        deadline = time.monotonic() + 5
        while True:
            try:
                lock.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ReviewConflictError('Another save is in progress. Refresh and retry.') from None
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def make_review_event(row, labels, reviewer, justification, evidence, decision, *, event_id=None):
    """Build an event only after explicit user submission; timestamp is server UTC."""
    event = dict(review_event_id=event_id or uuid.uuid4().hex, record_id=row['record_id'],
                 source_fingerprint=row['source_fingerprint'], reviewed_at=datetime.now(timezone.utc).isoformat(),
                 reviewer_code=reviewer.strip(), reviewer_decision=decision,
                 **labels, supporting_evidence=evidence.strip(), reviewer_notes=justification.strip())
    apply_review_events([row], [event])
    return event


def append_review_event(event, *, expected_latest_event_id, directory=None):
    """Validate and append one event, protecting prior bytes and rejecting stale forms."""
    from src.ui.runtime import app_mode

    if app_mode() != 'local':
        raise PermissionError('Saving real media reviews requires explicit local mode.')
    directory = Path(directory) if directory is not None else DATA_DIR
    with _ledger_lock(directory):
        rows = load_media_rows(directory)
        if rows is None:
            raise ValueError('The media dataset is unavailable.')
        load_review_queue(rows, directory)
        ledger = directory / 'media_review_events.csv'
        events = []
        if ledger.exists():
            with ledger.open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != REVIEW_FIELDS:
                    raise ValueError('Unexpected review-ledger header; existing history was not changed.')
                events = list(reader)
        previous = next((item for item in events if item['review_event_id'] == event['review_event_id']), None)
        if previous is not None:
            if previous == event:
                return False
            raise ReviewConflictError('This save identifier was already used for a different event.')
        row = next((item for item in rows if item['record_id'] == event['record_id']), None)
        if row is None or row['latest_review_event_id'] != expected_latest_event_id:
            raise ReviewConflictError('This article changed while you were reviewing it. Refresh before saving.')
        apply_review_events(rows, [event])
        buffer = io.StringIO(newline='')
        writer = csv.DictWriter(buffer, fieldnames=REVIEW_FIELDS)
        if not ledger.exists() or ledger.stat().st_size == 0:
            writer.writeheader()
        writer.writerow(event)
        with ledger.open('a', encoding='utf-8-sig', newline='') as handle:
            handle.write(buffer.getvalue())
            handle.flush()
            os.fsync(handle.fileno())
    return True


def completed_review_csv(rows):
    """Latest resolved decision per article; export only, never changes the ledger."""
    fields = ['record_id', 'published_at', 'publisher', 'original_url', 'review_event_id',
              'reviewer_name', 'reviewed_at', 'reviewer_decision', *CHOICES,
              'supporting_evidence', 'justification']
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        if row['review_status'] not in ('human_review_recorded', 'excluded_by_reviewer'):
            continue
        output = {field: row[field] for field in ('record_id', 'published_at', 'publisher', 'original_url', 'reviewed_at', 'reviewer_decision')}
        output.update(review_event_id=row['latest_review_event_id'], reviewer_name=row['reviewer_code'],
                      supporting_evidence=row['reviewed_supporting_evidence'], justification=row['reviewer_notes'])
        output.update({field: row['reviewed_' + field] for field in CHOICES})
        # Neutralise spreadsheet formula-like user input in the export; preserve ledger text exactly.
        writer.writerow({key: ("'" + value if value.startswith(('\t', '\r')) or value.lstrip().startswith(('=', '+', '-', '@')) else value)
                         for key, value in output.items()})
    return buffer.getvalue().encode('utf-8-sig')


def summarize_groups(rows, *, reviewed=False):
    """Exact counts, with an explicit common denominator for every group and basis."""
    output = []
    for category in CATEGORIES:
        group = [row for row in rows if (row['reviewed_source_category'] if reviewed else row['source_category']) == category
                 and (not reviewed or row['review_status'] == 'human_review_recorded')]
        def value(row, field):
            return row['reviewed_' + field] if reviewed else row[field]
        result = dict(source_category=category, basis='human_review_recorded' if reviewed else 'provisional_source_assisted',
                      denominator=len(group), human_reviews_recorded=sum(row['review_status'] == 'human_review_recorded' for row in group),
                      ambiguous_records=sum(bool(row['ambiguity_flags']) for row in group))
        for field, choices in CHOICES.items():
            if field == 'source_category':
                continue
            for label in choices:
                result[field + '_' + label] = sum(value(row, field) == label for row in group)
        result['both_brands_named'] = sum(value(row, 'ray_ban_mentioned') == 'yes' and value(row, 'meta_mentioned') == 'yes' for row in group)
        output.append(result)
    return output


def load_media_rows(directory=None):
    directory = Path(directory) if directory is not None else DATA_DIR
    articles = directory / 'articles.csv'
    quality_file = directory / 'dataset_quality.json'
    if not articles.exists() or not quality_file.exists():
        return None
    quality = json.loads(quality_file.read_text(encoding='utf-8'))
    if hashlib.sha256(articles.read_bytes()).hexdigest() != quality['sha256']:
        raise ValueError('Media source file changed; rerun quality checks and review before use.')
    rows = prepare_rows(read_csv(articles), quality)
    ledger = directory / 'media_review_events.csv'
    return apply_review_events(rows, read_csv(ledger)) if ledger.exists() else rows


def render_review_interface(rows):
    import pandas as pd
    import streamlit as st

    st.markdown('#### Review an article')
    try:
        queue = load_review_queue(rows)
    except (OSError, ValueError, KeyError) as exc:
        st.error(f'The human review template needs attention: {exc}')
        return
    reviewer = st.text_input('Media reviewer name', key='media_reviewer_name', max_chars=120,
                             help='Your name or agreed team identifier is saved locally in the existing reviewer_code field.')
    pending_only = st.checkbox('Show only pending or uncertain articles', value=True, key='media_pending_only')
    if pending_only:
        queue = [row for row in queue if row['review_status'] in ('pending_human_review', 'uncertain_pending_review')]
    queue.sort(key=lambda row: (not bool(row['ambiguity_flags']), row['published_at'], row['record_id']))
    if not queue:
        st.info('No pending articles. Clear the pending-only filter to inspect or revise completed reviews.')
        return
    by_id = {row['record_id']: row for row in queue}
    record_id = st.selectbox('Article to review', list(by_id), key='media_review_record',
                             format_func=lambda key: f"{by_id[key]['published_at']} · {by_id[key]['publisher']} · {by_id[key]['title']}")
    row = by_id[record_id]
    st.write(row['title'])
    st.caption(f"{row['published_at']} · {row['publisher']} · {row['record_id']} · {row['review_status']}")
    st.link_button('Open article source', row['original_url'])
    st.write('**Proposed labels — preserved separately from your decision**')
    st.json({field: row[field] for field in CHOICES})
    st.write('Supporting evidence: ' + row['supporting_evidence'])
    st.caption('Source locator: ' + row['evidence_locator'])
    st.caption('Review flags: ' + (row['ambiguity_flags'] or 'None beyond the required human review.'))
    st.caption('A Ray-Ban mention is not brand damage. Explicit here means a direct traditional-brand reference '
               'of any tone. Responsibility describes attributed roles or inquiry targets, not proven liability.')
    version = row['latest_review_event_id'] or 'initial'
    suffix = record_id + '_' + version
    actions = {'Confirm proposed labels': 'confirm', 'Correct classifications': 'correct',
               'Mark uncertain': 'uncertain', 'Exclude from analysis': 'exclude'}
    action = st.radio('Media review decision', list(actions), index=None, key='media_action_' + suffix)
    if row['latest_review_event_id']:
        st.caption(f"Latest saved reviewer: {row['reviewer_code']} · {row['reviewed_at']} (UTC offset shown).")
    with st.form('media_form_' + suffix):
        labels = {}
        for field, choices in CHOICES.items():
            initial = row['reviewed_' + field] or row[field]
            if action == 'Confirm proposed labels':
                initial = row[field]
            labels[field] = st.selectbox('Media ' + field.replace('_', ' '), choices,
                                         index=choices.index(initial), disabled=action == 'Confirm proposed labels')
        evidence = st.text_area('Media supporting evidence', row['reviewed_supporting_evidence'] or row['supporting_evidence'], max_chars=3000)
        reason = st.text_area('Short review justification', max_chars=1500)
        checked = st.checkbox('I reviewed the available source evidence and recorded any access or interpretation limitations.')
        st.caption('Saved timestamps are automatic UTC. Uncertain decisions remain pending and are excluded from reviewed findings. '
                   'Use unclear for individual unresolved labels where available. No decision is saved on refresh.')
        save = st.form_submit_button('Save media review', type='primary', disabled=action is None)
    if save:
        try:
            if not checked:
                raise ValueError('Explicitly confirm your source-evidence check before saving.')
            token_key = 'media_save_' + suffix
            event = make_review_event(row, labels, reviewer, reason, evidence, actions[action],
                                      event_id=st.session_state.setdefault(token_key, uuid.uuid4().hex))
            append_review_event(event, expected_latest_event_id=row['latest_review_event_id'])
            st.session_state['media_review_saved'] = True
            st.rerun()
        except (ValueError, PermissionError, OSError) as exc:
            st.error(f'Review not saved: {exc}')
    with st.expander('Review history for this article'):
        ledger = DATA_DIR / 'media_review_events.csv'
        events = [event for event in read_csv(ledger) if event['record_id'] == record_id] if ledger.exists() else []
        if events:
            st.dataframe(pd.DataFrame(events), hide_index=True)
        else:
            st.info('No human review events have been saved for this article.')


def render_real_media(*, allow_review=False):
    import pandas as pd
    import streamlit as st

    st.subheader('Real Media Evidence')
    st.caption('Genuine published sources only. Separate from synthetic customer scenarios, AI benchmarks '
               'and customer sentiment metrics. No inference or research database access runs here.')
    try:
        rows = load_media_rows()
    except (ValueError, KeyError) as exc:
        st.error(f'Media evidence needs review: {exc}')
        return
    if rows is None:
        st.info('The local media dataset is unavailable in this deployment. No synthetic replacement is used.')
        return
    if st.session_state.pop('media_review_saved', False):
        st.success('Media review appended locally. Original classifications and previous review events are unchanged.')
    progress = review_progress(rows)
    columns = st.columns(4)
    for column, label, value in zip(columns, ('Reviewed / total', 'Pending', 'Flagged', 'Disagreements'),
                                     (f"{progress['reviewed']}/{progress['total']}", progress['pending'], progress['flagged'], progress['disagreements'])):
        column.metric(label, value)
    st.caption(f"Reviewed means a current confirm/correct/exclude decision. {progress['uncertain']} uncertain cases remain pending. "
               'Flagged counts unresolved source flags or uncertainty. Disagreements counts latest completed labels differing '
               'from proposals, or exclusions; it is not an inter-rater reliability score.')
    included = sum(row['review_status'] == 'human_review_recorded' for row in rows)
    excluded = sum(row['review_status'] == 'excluded_by_reviewer' for row in rows)
    reviewed = included + excluded
    st.warning(f'{len(rows)} source-traceable records; {reviewed}/{len(rows)} have resolved human reviews '
               f'({included} included, {excluded} excluded). '
               'Provisional tables use assistant-assisted coding; reviewed tables use only recorded human labels. '
               'Neither represents customer sentiment findings. '
               'A direct traditional-brand reference can be positive or stylistic; it does not mean adverse spillover.')
    if included:
        st.write('Separately recorded human-review results (excluded records omitted)')
        st.dataframe(pd.DataFrame(summarize_groups(rows, reviewed=True)), hide_index=True)
    else:
        st.info('No included human-reviewed records support association estimates yet. '
                'An empty reviewed denominator is not evidence of zero spillover.')
    st.write('Provisional source-assisted results — not human-reviewed findings')
    st.dataframe(pd.DataFrame(summarize_groups(rows)), hide_index=True)
    st.caption('Each denominator is that source group’s collected record count. Responsibility codes describe '
               'explicit processing roles or inquiry targets, not established legal blame. Unstated/other-actor cases remain unclear.')
    from src.ui.runtime import app_mode
    if allow_review and app_mode() == 'local':
        st.download_button('Export completed media reviews (CSV)', completed_review_csv(rows),
                           'completed_media_reviews.csv', 'text/csv', disabled=progress['reviewed'] == 0,
                           help='Latest resolved decision per article, including exclusions. Pending/uncertain cases are omitted; formula-like text is escaped for spreadsheets.')
        render_review_interface(rows)
    else:
        st.info('Saving real reviews is available only in explicit local mode through app.py. Demo/cloud mode is read-only.')
    with st.expander('Inspect real source records and review status'):
        fields = ['record_id', 'published_at', 'publisher', 'original_url', 'source_category', 'privacy_related',
                  'ray_ban_mentioned', 'meta_mentioned', 'responsibility_attributed', 'wider_brand_association',
                  'association_direction', 'supporting_evidence', 'ambiguity_flags', 'reviewer_decision', 'review_status']
        st.dataframe(pd.DataFrame(rows)[fields], hide_index=True,
                     column_config={'original_url': st.column_config.LinkColumn('Original source')})
