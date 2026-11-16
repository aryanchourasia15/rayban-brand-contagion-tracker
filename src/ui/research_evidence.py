"""Offline sourced context and transparent synthetic outputs; never research storage."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_timeline():
    report = json.loads((ROOT / 'demo/research_timeline.json').read_text(encoding='utf-8'))
    if report.get('kind') != 'sourced_context_not_customer_data':
        raise ValueError('Timeline must be identified as sourced context, not customer data.')
    return report


def load_case_study():
    path = ROOT / 'demo/case_study_results.json'
    if not path.exists():
        return None
    report = json.loads(path.read_text(encoding='utf-8'))
    if report.get('synthetic_only') is not True:
        raise ValueError('Only synthetic case-study results can appear in this demonstration.')
    fixture = json.loads((ROOT / 'tests/fixtures/contagion_case_study_24.json').read_text(encoding='utf-8'))
    fingerprint = hashlib.sha256(json.dumps(fixture['examples'], sort_keys=True).encode()).hexdigest()
    if fixture.get('is_synthetic') is not True or report['fixture_sha256'] != fingerprint or fixture['sha256'] != fingerprint:
        raise ValueError('Case-study provenance does not match the synthetic fixture.')
    references = {case['case']: case for case in fixture['examples']}
    if len({row['case'] for row in report['results']}) != len(report['results']):
        raise ValueError('Case-study results contain duplicate cases.')
    for row in report['results']:
        case = references.get(row['case'])
        if case is None or row['text'] != case['text'] or row['reference'] != case['labels']:
            raise ValueError('Case-study text or reference mismatch.')
    if report.get('completed') and len(report['results']) != len(references):
        raise ValueError('Completed case study has missing results.')
    return report


def render_timeline():
    import pandas as pd
    import streamlit as st

    report = load_timeline()
    st.subheader('Verified context, not customer sentiment')
    st.caption(f"Reviewed through {report['reviewed_at']}. {report['methodology']}")
    frame = pd.DataFrame(report['events'])
    if frame.empty:
        st.info('No sourced events are available.')
        return
    years = sorted(frame['date'].str[:4].unique())
    selected = st.multiselect('Timeline years', years, key='context_years')
    if selected:
        frame = frame.loc[frame['date'].str[:4].isin(selected)]
    st.dataframe(frame[['date', 'title', 'evidence_type', 'description', 'publisher', 'source_url']],
                 hide_index=True, column_config={'source_url': st.column_config.LinkColumn('Source')})
    for row in frame.to_dict('records'):
        with st.expander(f"{row['date']} · {row['title']}"):
            st.write(f"**{row['evidence_type']}** · {row['description']}")
            st.caption(f"Date basis: {row['date_basis']}. Source published {row['source_published_at']}. "
                       f"Latest listed update: {row['source_updated_at'] or 'not listed'}. Verified {row['verified_at']}.")
            st.write('Limit: ' + row['limitation'])
            st.link_button('Read source', row['source_url'])


def render_case_study():
    import pandas as pd
    import streamlit as st

    st.subheader('24 synthetic scenarios · actual recorded local AI')
    st.warning('Invented scenarios, not customer records. Actual Qwen outputs are preserved, including '
               'rejections. These illustrative examples do not establish real-world accuracy or brand damage.')
    report = load_case_study()
    if report is None or not report['results']:
        st.info('No recorded local case-study results are available. No inference runs automatically.')
        return
    if not report.get('completed'):
        st.warning('Incomplete run; the results shown are partial.')
    st.caption(f"Model {report['model']['model_name']} · prompt {report['prompt_version']} · "
               f"recorded {report['created_at']}. No cloud inference or live model dependency.")
    rows = report['results']
    frame = pd.DataFrame([dict(case=row['case'], category=row['category'],
        status=row['status'], reference_spillover=row['reference']['spillover'],
        predicted_spillover=(row.get('parsed_output') or {}).get('spillover', 'unparseable'),
        seconds=row['seconds']) for row in rows])
    categories = st.multiselect('Synthetic case categories', sorted(frame['category'].unique()), key='case_categories')
    status = st.multiselect('Case safeguard status', sorted(frame['status'].unique()), key='case_status')
    visible = frame
    if categories:
        visible = visible.loc[visible['category'].isin(categories)]
    if status:
        visible = visible.loc[visible['status'].isin(status)]
    st.dataframe(visible, hide_index=True)
    if not visible.empty:
        case_id = st.selectbox('Inspect actual local output', visible['case'].tolist(), key='case_output')
        row = next(row for row in rows if row['case'] == case_id)
        st.text(row['text'])
        cols = st.columns(2)
        with cols[0]:
            st.caption('Authored reference labels · not independent human validation')
            st.json(row['reference'])
        with cols[1]:
            st.caption('Actual model response · rejected output is not an accepted classification')
            st.code(row['raw_output'] or '(No model output)', language='json')
        st.write(f"Safeguard outcome: **{row['status']}**. " + (row.get('validation') or row.get('error') or ''))
    with st.expander('Case-study metrics and provenance · all cases, unaffected by filters'):
        st.caption('Raw metrics include evaluable rejected outputs. Accepted metrics use only the accepted subset; '
                   'rejections are abstentions. Neither is a population estimate. Confidence is uncalibrated.')
        st.json({key: value for key, value in report.items() if key != 'results'})
    with st.expander('AI evaluation summary · v1 versus v2 and observed failure patterns'):
        st.markdown((ROOT / 'docs/AI_EVALUATION_SUMMARY.md').read_text(encoding='utf-8'))


def render_strategy():
    import streamlit as st

    st.markdown((ROOT / 'docs/STRATEGIC_IMPLICATIONS.md').read_text(encoding='utf-8'))
