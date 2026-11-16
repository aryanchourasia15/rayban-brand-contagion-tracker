"""Native Streamlit interface; all ingestion uses the existing backend."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from src.config import DEFAULT_GDELT_QUERIES, VALID_SOURCES, VALID_SOURCE_TYPES, VALID_RELEVANCE_FLAGS
from src.data.db import get_database_summary
from src.data.importers.file_importer import (
    DEFAULT_COLUMN_ALIASES, parse_file_to_rows, detect_column_mapping,
    validate_and_transform_rows, import_file, generate_csv_template,
)
from src.data.connectors.gdelt import preview_gdelt
from src.config import DEFAULT_GUARDIAN_QUERIES
from src.data.connectors.guardian import GUARDIAN_ENABLED, preview_guardian, import_guardian_preview
from src.ui.data_access import load_records, load_history, import_news_preview


def show_result(result):
    st.success(f"{result['imported']} imported · {result['duplicates']} duplicate attempts · {result['invalid']} invalid")


def overview():
    summary = get_database_summary()
    cols = st.columns(4)
    for col, label, key in zip(cols,
                              ['Real records', 'Customer discussions', 'News / media', 'Duplicate attempts'],
                              ['total_records', 'customer_discussions', 'media_records', 'total_duplicates_logged']):
        col.metric(label, summary[key])
    latest = summary['latest_batch']
    st.caption(f"Latest import (UTC): {latest['started_at'] if latest else 'No imports yet'} · Synthetic data excluded")
    st.markdown('### Evidence before inference')
    st.write('Is the privacy controversy confined to Ray-Ban Meta, or does it affect perceptions of the wider Ray-Ban brand?')
    st.info('Media coverage and customer discussions are separate evidence streams. Public online discussions are not representative of all customers. Relevance flags support research triage; they do not establish sentiment or brand damage.')
    if not summary['total_records']:
        st.info('Your research dataset is empty. Start with a CSV/JSON upload or preview recent GDELT news.')


def file_import():
    st.subheader('Bring your evidence')
    st.caption('Map columns, review validation, then confirm the import. Original text is preserved.')
    st.download_button('Download CSV template', generate_csv_template(), 'research_template.csv', 'text/csv')
    upload = st.file_uploader('CSV or JSON dataset', type=['csv', 'json'])
    if upload is None:
        return
    content = upload.getvalue()
    file_format = upload.name.rsplit('.', 1)[-1].lower()
    try:
        rows, headers = parse_file_to_rows(content, file_format=file_format)
    except Exception as exc:
        st.error(f'Unable to parse file: {exc}')
        return
    if not rows:
        st.info('This file contains no records.')
        return
    st.caption(f'{len(rows):,} rows detected')
    file_key = hashlib.sha256(content).hexdigest()[:16]
    cols = st.columns(2)
    source = cols[0].selectbox('Default source', VALID_SOURCES, index=2)
    forced_type = {'News': 'media', 'Reddit': 'customer_discussion'}.get(source)
    source_type = cols[1].selectbox('Default evidence type', VALID_SOURCE_TYPES,
                                  index=1 if forced_type == 'media' else 0,
                                  disabled=bool(forced_type), key=f'type_{source}')
    st.caption('Platform rules apply per row: News → media; Reddit → customer discussion. Conflicting explicit values are rejected.')
    cols = st.columns(2)
    order = cols[0].selectbox('Numeric date order', ['Reject ambiguous dates', 'Day first (DD/MM/YYYY)', 'Month first (MM/DD/YYYY)'])
    utc_offset = cols[1].number_input('UTC offset for dates without timezone (hours)', min_value=-12.0,
                                     max_value=14.0, value=0.0, step=0.5)
    st.caption('ISO dates with explicit offsets are converted to UTC. The fixed offset applies to naive dates; use explicit offsets when daylight saving time varies.')
    day_first = None if order.startswith('Reject') else order.startswith('Day')
    default_tz = timezone(timedelta(hours=utc_offset))
    mapping = {}
    detected = detect_column_mapping(headers)
    with st.expander('Column mappings', expanded=True):
        options = ['(use canonical field if present)'] + headers
        cols = st.columns(2)
        for index, field in enumerate(DEFAULT_COLUMN_ALIASES):
            chosen = cols[index % 2].selectbox(field, options,
                         index=options.index(detected[field]) if field in detected else 0,
                         key=f'mapping_{file_key}_{field}')
            mapping[field] = chosen if chosen != options[0] else field
    settings = dict(file_format=file_format, column_mapping=mapping, default_source=source,
                    default_source_type=source_type, day_first=day_first, default_tz=default_tz)
    signature = hashlib.sha256(content + repr(settings).encode()).hexdigest()
    if st.button('Validate & preview file', type='primary'):
        try:
            valid, invalid = validate_and_transform_rows(rows, column_mapping=mapping,
                               default_source=source, default_source_type=source_type,
                               day_first=day_first, default_tz=default_tz)
            st.session_state['file_preview'] = (signature, valid, invalid)
        except Exception as exc:
            st.error(f'Validation failed: {exc}')
            st.session_state.pop('file_preview', None)
    preview = st.session_state.get('file_preview')
    if not preview or preview[0] != signature:
        st.caption('Validate the current file and settings to enable import.')
        return
    _, valid, invalid = preview
    st.write(f'{len(valid):,} valid rows · {len(invalid):,} invalid rows')
    if valid:
        st.dataframe(pd.DataFrame(valid[:10]).drop(columns=['raw_payload'], errors='ignore'), hide_index=True)
    if invalid:
        st.warning('Invalid rows will be rejected. Review all row-level errors below.')
        st.dataframe(pd.DataFrame([{'row': row['row_number'], 'errors': '; '.join(row['errors']),
                                    'original_data': json.dumps(row['raw_data'], ensure_ascii=False)} for row in invalid]), hide_index=True)
    confirmed = st.checkbox('I reviewed this preview and confirm importing the valid rows.', key=f'file_confirm_{signature}')
    if st.button('Import reviewed file', disabled=not (confirmed and valid)):
        try:
            result = import_file(content, **settings)
            st.session_state['import_result'] = result
            st.session_state.pop('file_preview', None)
            st.rerun()
        except Exception as exc:
            st.error(f'Import failed: {exc}')


def gdelt_collection():
    st.subheader('Recent news, traceable sources')
    st.caption('GDELT supplies headlines and metadata, not full article text. These records are media evidence.')
    st.info('The connector supports a rolling ~90-day news window, up to 250 articles per query. Import historical evidence from 2023–2026 through CSV/JSON.')
    with st.form('gdelt_search'):
        preset = st.selectbox('Research query', DEFAULT_GDELT_QUERIES + ['Custom query'])
        custom = st.text_input('Custom query (used when selected above)')
        cols = st.columns(3)
        today = datetime.now(timezone.utc).date()
        start = cols[0].date_input('From (UTC)', today - timedelta(days=30))
        end = cols[1].date_input('Through (UTC)', today)
        maximum = cols[2].number_input('Maximum articles', 1, 250, 25)
        submitted = st.form_submit_button('Search & preview news', type='primary')
    if submitted:
        st.session_state.pop('news_preview', None)
        query = custom if preset == 'Custom query' else preset
        try:
            with st.spinner('Searching GDELT; transient errors may trigger backoff retries…'):
                end_time = datetime.now(timezone.utc).isoformat() if end == today else f'{end}T23:59:59Z'
                result = preview_gdelt(query, start_date=f'{start}T00:00:00Z',
                                      end_date=end_time, max_records=int(maximum))
            if not result['success']:
                st.error(result.get('error', 'GDELT search failed.'))
            else:
                st.session_state['news_preview'] = result
        except Exception as exc:
            st.error(f'GDELT could not complete the request: {exc}')
    result = st.session_state.get('news_preview')
    if not result:
        return
    if result.get('warning'):
        st.warning(result['warning'])
    records = result['preview_records']
    st.write(f"Reviewed snapshot: {result['query']} · {len(records)} valid · {result['invalid_count']} invalid")
    if not records:
        st.info('No valid articles returned. Try another query or date range.')
        return
    st.dataframe(pd.DataFrame(records)[['title', 'original_url', 'published_at', 'relevance_flag']],
                 column_config={'original_url': st.column_config.LinkColumn('Source URL')}, hide_index=True)
    snapshot_key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    confirmed = st.checkbox('I confirm importing these previewed articles.', key=f'news_confirm_{snapshot_key}')
    if st.button('Import reviewed news', disabled=not confirmed):
        try:
            st.session_state['import_result'] = import_news_preview(records, result['query'], result['invalid_count'])
            st.session_state.pop('news_preview', None)
            st.rerun()
        except Exception as exc:
            st.error(f'News import failed: {exc}')


def guardian_collection():
    st.subheader('Historical news · The Guardian')
    st.caption('Publisher: The Guardian · Guardian API · Headline-only records, not full article bodies.')
    st.markdown('[Guardian access](https://open-platform.theguardian.com/access/) · '
                '[Applicable terms](https://www.theguardian.com/open-platform/terms-and-conditions)')
    if not GUARDIAN_ENABLED:
        st.session_state.pop('guardian_preview', None)
        st.warning('Guardian collection and import are disabled pending licence clarification.')
        st.info('The standard developer terms restrict AI/text-data analysis and require refresh '
                'or deletion within 24 hours. Our historical SQLite research dataset requires explicit '
                'permission covering academic analysis, AI-assisted classification, human validation '
                'and the intended local retention period. A developer key or a permission-reference '
                'value alone does not establish that permission. No requests or imports are enabled.')
        return
    st.info('Use permitted non-commercial research access. Configure GUARDIAN_API_KEY and '
            'GUARDIAN_PERMISSION_REFERENCE in the server environment. The permission must cover '
            'this research analysis and the intended retention period. Full article bodies are never requested or stored.')
    configured = bool(os.getenv('GUARDIAN_API_KEY', '').strip() and
                      os.getenv('GUARDIAN_PERMISSION_REFERENCE', '').strip())
    if not configured:
        st.warning('Guardian collection is unconfigured. Add the required environment variables, then restart Streamlit.')
        return
    with st.form('guardian_search'):
        preset = st.selectbox('Guardian query', DEFAULT_GUARDIAN_QUERIES + ['Custom query'])
        custom = st.text_input('Custom Guardian query')
        cols = st.columns(4)
        start = cols[0].date_input('Guardian start date (UTC)', datetime(2023, 1, 1).date())
        end = cols[1].date_input('Guardian end date (UTC)', datetime.now(timezone.utc).date())
        maximum = cols[2].number_input('Maximum Guardian results', 1, 1000, 50)
        page = cols[3].number_input('Starting page', 1, value=1)
        submitted = st.form_submit_button('Search & preview Guardian', type='primary')
    st.caption('Up to 50 results/page. Requests are paced; HTTP 429 stops collection. '
               'The free developer tier permits 500 requests/day. Other tools using the same key share that quota.')
    if submitted:
        st.session_state.pop('guardian_preview', None)
        with st.spinner('Searching the Guardian archive…'):
            result = preview_guardian(custom if preset == 'Custom query' else preset,
                                      start.isoformat(), end.isoformat(), int(maximum), int(page))
        if result['success']:
            st.session_state['guardian_preview'] = result
        else:
            st.error(result['error'])
    result = st.session_state.get('guardian_preview')
    if not result:
        return
    records = result['preview_records']
    st.write(f"Preview: {result['query']} · {len(records)} valid · {result['invalid_count']} invalid · "
             f"{result['total_found']} API matches · {result['pages_fetched']} pages requested")
    st.caption(f"Next page: {result.get('next_page') or 'End of results'}. Importing saves this exact snapshot without refetching.")
    if result.get('partial_page'):
        st.caption('The result cap cut a page short. Resume at the indicated page with the same page size; reviewed overlaps will deduplicate.')
    if not records:
        st.info('No valid Guardian articles returned for this search.')
        return
    st.dataframe(pd.DataFrame(records)[['title', 'original_url', 'published_at', 'collection_method']],
                 hide_index=True, column_config={'original_url': st.column_config.LinkColumn('The Guardian source')})
    identity = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    confirmed = st.checkbox('I reviewed these headline-only Guardian records and confirm import.', key=f'guardian_confirm_{identity}')
    if st.button('Import reviewed Guardian headlines', disabled=not confirmed):
        try:
            st.session_state['import_result'] = import_guardian_preview(result)
            st.session_state.pop('guardian_preview', None)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def explorer():
    st.subheader('Inspect the evidence')
    search = st.text_input('Search original text or title')
    cols = st.columns(3)
    sources = cols[0].multiselect('Source', VALID_SOURCES)
    types = cols[1].multiselect('Evidence type', VALID_SOURCE_TYPES)
    relevance = cols[2].multiselect('Relevance', VALID_RELEVANCE_FLAGS)
    dates = {}
    with st.expander('Date filters (inclusive, UTC)'):
        for field, label in [('published', 'Publication date'), ('collected', 'Collection date')]:
            cols = st.columns(2)
            dates[f'{field}_from'] = cols[0].date_input(f'{label}: from', value=None, key=f'{field}_from')
            dates[f'{field}_to'] = cols[1].date_input(f'{label}: through', value=None, key=f'{field}_to')
            if dates[f'{field}_from'] and dates[f'{field}_to'] and dates[f'{field}_from'] > dates[f'{field}_to']:
                st.warning(f'{label}: the start must be before the end.')
                return
    frame = load_records(sources=sources, source_types=types, relevance_flags=relevance, search=search, **dates)
    st.caption(f'{len(frame):,} real records match · media = journalism; customer_discussion = public customer voice')
    if frame.empty:
        st.info('No records match these filters.')
        return
    st.dataframe(frame, hide_index=True, column_config={
        'canonical_url': st.column_config.LinkColumn('Source URL'),
        'original_url': st.column_config.LinkColumn('Original URL'),
        'source_type': st.column_config.TextColumn('Evidence type'),
    })
    record_id = st.selectbox('Read original record', frame['record_id'].tolist())
    record = frame.loc[frame['record_id'] == record_id].iloc[0]
    st.caption(f"{record['source_type']} · {record['source']} · {record['published_at'] or 'Publication date unavailable'}")
    st.text(record['text'])
    st.download_button('Export filtered CSV', frame.to_csv(index=False).encode('utf-8-sig'),
                       'rayban_research_filtered.csv', 'text/csv')


def history():
    st.subheader('Collection audit trail')
    frame = load_history()
    if frame.empty:
        st.info('No real import batches yet.')
    else:
        st.dataframe(frame, hide_index=True)


def render_collection_centre():
    st.markdown('''<style>
    .block-container {max-width: 1400px; padding-top: 2.4rem;}
    h1 {letter-spacing: -.045em;} h2,h3 {letter-spacing: -.025em;}
    [data-testid="stMetric"] {border-top: 2px solid #C62430; padding: 1rem 0;}
    </style>''', unsafe_allow_html=True)
    with st.sidebar:
        st.markdown('### RAY-BAN')
        st.caption('CUSTOMER TRUST INTELLIGENCE')
        st.divider()
        st.caption('HEC Paris · Strategic Management\n\nResearch period 2023–2026\n\nStrategic horizon 2030')
        if st.button('Refresh dataset'):
            st.rerun()
    st.caption('RESEARCH OPERATIONS / DATA FOUNDATION')
    st.title('Data Collection Centre')
    st.write('Collect, validate and explore the evidence behind customer trust.')
    result = st.session_state.pop('import_result', None)
    if result:
        show_result(result)
    tabs = st.tabs(['Overview', 'CSV / JSON import', 'GDELT news', 'Guardian news', 'Dataset explorer', 'Import history'])
    for tab, render in zip(tabs, [overview, file_import, gdelt_collection, guardian_collection, explorer, history]):
        with tab:
            try:
                render()
            except Exception as exc:
                st.error(f'This section could not load: {exc}')
