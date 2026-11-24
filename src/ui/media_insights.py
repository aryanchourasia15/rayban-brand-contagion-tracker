"""Read-only media coding snapshot, separate from simulated customer analytics."""
import json
from pathlib import Path

from src.analysis.simulation import fingerprint
from src.ui.media_evidence import CHOICES, CATEGORIES, summarize_groups, review_progress

ROOT = Path(__file__).resolve().parents[2]
KIND = 'public_media_coding_snapshot_not_customer_data'
RECORD_FIELDS = {'record_id', 'source_fingerprint', 'association_direction', 'review_status',
                 'ambiguity_flags', *CHOICES, *('reviewed_' + field for field in CHOICES)}
TOP_FIELDS = {'kind', 'as_of', 'source_csv_sha256', 'source_manifest_sha256',
              'review_ledger_sha256', 'records', 'records_sha256'}
CATEGORY_NAMES = dict(independent_media='Independent media', company_statements='Company statements',
                      official_regulatory='Official / regulatory sources')
STATUSES = {'pending_human_review', 'uncertain_pending_review', 'excluded_by_reviewer', 'human_review_recorded'}


def validate_snapshot(report, manifest):
    if set(report) != TOP_FIELDS or report['kind'] != KIND:
        raise ValueError('Only the public-safe media coding contract may be loaded.')
    if (report['source_csv_sha256'] != manifest['source_sha256'] or
            report['source_manifest_sha256'] != manifest['sha256']):
        raise ValueError('Media coding does not match the frozen 32-source manifest.')
    rows = report['records']
    if len(rows) != 32 or len({r['record_id'] for r in rows}) != 32:
        raise ValueError('Expected one coding record for each of the 32 sources.')
    if {r['record_id'] for r in rows} != {r['source_id'] for r in manifest['sources']}:
        raise ValueError('A media coding record has no bibliographic source.')
    if fingerprint(rows) != report['records_sha256']:
        raise ValueError('Media coding snapshot changed.')
    for row in rows:
        if set(row) != RECORD_FIELDS or row['review_status'] not in STATUSES:
            raise ValueError('Invalid or private fields in media snapshot.')
        if not all(isinstance(value, str) for value in row.values()):
            raise ValueError('Media coding fields must be strings.')
        for field, choices in CHOICES.items():
            if row[field] not in choices or row['reviewed_' + field] not in ('', *choices):
                raise ValueError('Invalid media coding label.')
            if row['review_status'] != 'pending_human_review' and not row['reviewed_' + field]:
                raise ValueError('Recorded review states require recorded labels.')
    return report


def load_media_snapshot():
    from src.ui.synthetic_reactions import load_public_sources
    report = json.loads((ROOT/'demo/media_analysis.json').read_text(encoding='utf-8'))
    return validate_snapshot(report, load_public_sources())


def filter_media_records(rows, *, categories=(), reviewed=False):
    category_field = 'reviewed_source_category' if reviewed else 'source_category'
    return [row for row in rows
            if (not reviewed or row['review_status'] == 'human_review_recorded')
            and (not categories or row[category_field] in categories)]


def media_totals(rows, *, reviewed=False):
    groups = summarize_groups(rows, reviewed=reviewed)
    fields = ('privacy_related_yes', 'ray_ban_mentioned_yes', 'meta_mentioned_yes', 'both_brands_named',
              'wider_brand_association_explicit', 'responsibility_attributed_Meta',
              'responsibility_attributed_Ray-Ban', 'responsibility_attributed_both', 'responsibility_attributed_unclear')
    return {'denominator': sum(g['denominator'] for g in groups),
            **{field: sum(g[field] for g in groups) for field in fields}}


def render_media_insights():
    import pandas as pd
    import streamlit as st
    from src.ui.synthetic_reactions import load_public_sources

    st.subheader('Real Media Insights')
    st.write('What this collected media sample says about privacy coverage, brand association and attributed roles. '
             'These are media records, not customer opinions.')
    try:
        report = load_media_snapshot()
        manifest = load_public_sources()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f'The public media analysis snapshot needs attention: {exc}')
        return
    progress = review_progress(report['records'])
    st.warning(f"{progress['reviewed']}/32 resolved human reviews; {progress['pending']}/32 pending. "
               'Source-assisted analytical labels remain provisional. Genuine source provenance does not validate the coding.')
    st.caption(f"Coding snapshot as of {report['as_of']}. Refreshing the app does not refresh local review events. "
               'Reviewer identities, notes and article bodies are not distributed. Human-review status records decisions, not proof of reviewer independence.')
    categories = st.multiselect('Media source categories', CATEGORIES, format_func=CATEGORY_NAMES.get,
                               key='media_insights_categories')
    basis = st.radio('Media analytical basis', ['Provisional source-assisted coding', 'Human-reviewed coding only'],
                     key='media_insights_basis', horizontal=True)
    reviewed = basis == 'Human-reviewed coding only'
    rows = filter_media_records(report['records'], categories=categories, reviewed=reviewed)
    totals = media_totals(rows, reviewed=reviewed)
    n = totals['denominator']
    st.caption('Denominators are included records in the selected source groups—not all news coverage. '
               'Human-reviewed mode excludes pending, uncertain and excluded records. No synthetic records contribute.')
    if not n:
        st.info('No included human-reviewed records support findings for this selection. '
                'An empty denominator is not evidence of no privacy concern or brand damage.')
        return
    cols = st.columns(4)
    for col, label, field in zip(cols, ('Privacy-related coverage', 'Ray-Ban named', 'Meta named', 'Direct traditional-brand references'),
                                ('privacy_related_yes', 'ray_ban_mentioned_yes', 'meta_mentioned_yes', 'wider_brand_association_explicit')):
        col.metric(label, f'{totals[field]}/{n}')
    group_rows = []
    for group in summarize_groups(rows, reviewed=reviewed):
        denominator = group['denominator']
        if not denominator:
            continue
        group_rows.append({'Source category': CATEGORY_NAMES[group['source_category']], 'Records': denominator,
            **{label: f'{group[field]}/{denominator}' for label, field in (
                ('Privacy-related', 'privacy_related_yes'), ('Ray-Ban named', 'ray_ban_mentioned_yes'),
                ('Meta named', 'meta_mentioned_yes'), ('Both named', 'both_brands_named'),
                ('Direct traditional-brand reference', 'wider_brand_association_explicit'))}})
    st.markdown('#### Coverage and brand naming')
    st.dataframe(pd.DataFrame(group_rows), hide_index=True)
    st.caption('A direct traditional-brand reference can favour traditional frames or describe styling. '
               'It is not equivalent to negative customer spillover. Naming is conditioned by how this corpus was collected.')
    st.markdown('#### Meta versus Ray-Ban: attributed roles')
    attribution = []
    for group in summarize_groups(rows, reviewed=reviewed):
        denominator = group['denominator']
        if denominator:
            attribution.append({'Source category': CATEGORY_NAMES[group['source_category']],
                **{label: f"{group['responsibility_attributed_' + code]}/{denominator}" for label, code in
                   (('Meta', 'Meta'), ('Ray-Ban', 'Ray-Ban'), ('Both partners', 'both'), ('Unclear / other actor', 'unclear'))}})
    st.dataframe(pd.DataFrame(attribution), hide_index=True)
    st.write(f"This selected coding attributes a privacy/data-processing role or inquiry target to Meta in "
             f"{totals['responsibility_attributed_Meta']}/{n} records, Ray-Ban in {totals['responsibility_attributed_Ray-Ban']}/{n}, "
             f"and both in {totals['responsibility_attributed_both']}/{n}. "
             f"{totals['responsibility_attributed_unclear']}/{n} remain unclear or involve other actors.")
    st.caption('These codes are attributed roles or inquiry targets, not legal liability or customer blame. '
               'No coded Ray-Ban attribution does not establish that Ray-Ban has no responsibility. Company statements are not independent verification; inquiries are not adjudicated findings.')
    by_id = {r['source_id']: r for r in manifest['sources']}
    st.markdown('#### What reaches traditional Ray-Ban eyewear?')
    direct = [r for r in rows if r[('reviewed_' if reviewed else '') + 'wider_brand_association'] == 'explicit']
    if direct:
        for row in direct:
            source = by_id[row['record_id']]
            st.link_button(source['publisher'] + ' · ' + source['title'], source['url'])
            descriptions = {
                'positive_traditional_brand_comparison': 'The existing source-assisted interpretation favours traditional eyewear in a direct comparison. It is not evidence of wider-brand damage.',
                'traditional_style_continuity': 'The existing source-assisted interpretation concerns continuity with classic Ray-Ban styling alongside product criticism. It is not evidence of wider-brand damage.',
            }
            st.write(descriptions.get(row['association_direction'], 'A direct traditional-brand reference is coded; its tone and meaning require source review.'))
            st.caption('Original source-assisted context · current review status: ' + row['review_status'].replace('_', ' '))
    else:
        st.info('No direct traditional-brand references are coded in this selection. This does not establish absence of brand risk.')
    with st.expander('Source-level coding and original references', expanded=True):
        data = []
        for row in rows:
            source = by_id[row['record_id']]
            prefix = 'reviewed_' if reviewed else ''
            data.append({'Record ID': row['record_id'], 'Date': source['published_at'], 'Publisher': source['publisher'],
                         'Headline': source['title'], 'Original URL': source['url'],
                         'Category': CATEGORY_NAMES[row[prefix + 'source_category']],
                         'Privacy-related': row[prefix + 'privacy_related'],
                         'Ray-Ban named': row[prefix + 'ray_ban_mentioned'], 'Meta named': row[prefix + 'meta_mentioned'],
                         'Responsibility': row[prefix + 'responsibility_attributed'],
                         'Traditional-brand reference': row[prefix + 'wider_brand_association'],
                         'Review status': row['review_status'], 'Review flags': row['ambiguity_flags']})
        st.dataframe(pd.DataFrame(data), hide_index=True,
                     column_config={'Original URL': st.column_config.LinkColumn('Original source')})
