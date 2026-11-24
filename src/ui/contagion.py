"""Brand-contagion dashboard: explicit local inference, separate demo and review flows."""
import json

import pandas as pd
import streamlit as st

from src.analysis.engine import classify_batch
from src.analysis.evaluation import evaluate_pairs, evaluate_research
from src.analysis.ollama_client import local_model_status, LocalModelError
from src.analysis.schema import LABELS, TOPICS, validate_labels
from src.analysis.storage import append_review, get_history
from src.ui.contagion_data import (
    MIN_SAMPLE, approved_discussions, classified_discussions, demo_discussions,
    filter_discussions, select_label_basis, spillover_rate, breakdown,
    sentiment_comparison, spillover_trends, highlighted_evidence,
)


def classification_panel(demo):
    st.subheader('Local intelligence, explicit control')
    if demo:
        st.info('Demo uses existing synthetic reference labels. No AI has run on these examples; '
                'no Ollama connection, permission grant or database insertion is needed.')
        st.dataframe(pd.DataFrame([dict(case=row['record_id'], sentiment=row['prediction']['sentiment'],
                                       spillover=row['prediction']['spillover']) for row in demo_discussions()]), hide_index=True)
        return
    st.caption('Only real, valid customer discussions with an active verified permission grant appear here. '
               'News headlines are excluded. Classification never runs on refresh.')
    if st.button('Check local Ollama', key='contagion_check_ollama'):
        st.session_state.pop('contagion_ollama', None)
        try:
            st.session_state['contagion_ollama'] = local_model_status()
        except LocalModelError as exc:
            st.error(str(exc))
    status = st.session_state.get('contagion_ollama')
    if status is None:
        st.info('Connection not checked. Start local-only Ollama, then check installed models.')
        return
    st.success(f"Local Ollama {status['version']} · {len(status['models'])} installed model candidates")
    st.caption('Availability is rechecked before inference. Only loopback connections are used; '
               'cloud models, redirects and automatic downloads are blocked.')
    if not status['models']:
        st.warning('No usable installed models found. No model will be downloaded automatically.')
        return
    model = st.selectbox('Installed local model', status['models'])
    records = approved_discussions()
    if not records:
        st.info('No approved customer discussions are available. Permission verification remains a backend operation; '
                'a reviewer must verify actual authorization before granting access.')
        return
    by_id = {row['record_id']: row for row in records}
    selected = st.multiselect('Approved comments to classify (one or a batch of up to 50)', list(by_id),
                              format_func=lambda key: f"{by_id[key]['source']} · {by_id[key]['text'][:85]} · {key}")
    if selected:
        st.dataframe(pd.DataFrame([dict(record_id=key, source=by_id[key]['source'],
                     text=by_id[key]['text'], published_at=by_id[key]['published_at']) for key in selected]), hide_index=True)
    confirm_key = 'contagion_confirm_' + str((model, tuple(selected)))
    confirmed = st.checkbox('I approve local classification of exactly these selected records.', key=confirm_key)
    if st.button('Classify approved selection', type='primary', disabled=not confirmed or not 1 <= len(selected) <= 50):
        with st.spinner('Classifying locally; each record is checked again for permission…'):
            try:
                result = classify_batch(selected, model)
                st.session_state['contagion_result'] = result
                st.rerun()
            except Exception:
                st.error('Local classification could not complete. Inspect the backend history before retrying.')


def analytics_panel(rows, demo):
    st.subheader('Does product criticism reach the brand?')
    if not demo:
        rows = select_label_basis(rows, 'Human-reviewed labels')
        st.caption('Research analytics use human-reviewed labels from the latest eligible AI run per record. '
                   'Unreviewed AI predictions, revoked permissions, media and synthetic records are excluded.')
    else:
        rows = select_label_basis(rows)
        st.caption('SIMULATED COUNTS · Curated fixture references, with no claim of AI accuracy or empirical findings.')
    if not rows:
        st.info('No human-reviewed research records are available. See the sourced timeline, synthetic AI case study and benchmark for context.')
        return
    available_sources = sorted({row['source'] for row in rows})
    selected_sources = st.multiselect('Analytics sources', available_sources, key=f'analytics_sources_{demo}')
    if selected_sources:
        rows = [row for row in rows if row['source'] in selected_sources]
    available_years = sorted(spillover_trends(rows)['year'].unique().tolist())
    selected_years = (st.multiselect('Analytics publication years', available_years, key=f'analytics_years_{demo}')
                      if available_years else [])
    if selected_years:
        rows = [row for row in rows if row.get('published_at') and
                str(pd.to_datetime(row['published_at'], utc=True, errors='coerce').year) in selected_years]
    rate = spillover_rate(rows)
    cols = st.columns(4)
    cols[0].metric('Demo examples' if demo else 'Reviewed discussions', len(rows))
    cols[1].metric('Negative privacy discussions', rate['denominator'])
    cols[2].metric('Explicit in that cohort', rate['explicit'])
    cols[3].metric('Brand Spillover Rate', 'Insufficient sample' if rate['percent'] is None else f"{rate['percent']:.1f}%")
    st.caption(f"Rate = explicit spillover within negative privacy discussions / negative privacy discussions. "
               f"Current fraction: {rate['explicit']}/{rate['denominator']}. Mixed sentiment is outside this denominator. "
               f"Percentages require at least {MIN_SAMPLE} denominator records; this display rule is not statistical significance.")
    if len(rows) < MIN_SAMPLE:
        st.warning('Small sample: counts describe these records only. They cannot establish population-wide brand damage.')
    if not rows:
        st.info('No human-reviewed research records match yet. Use Customer voice and Human validation to inspect permitted predictions.')
        return
    cols = st.columns(2)
    with cols[0]:
        st.markdown('#### Product versus traditional brand sentiment')
        comparison = sentiment_comparison(rows)
        if comparison.empty:
            st.info('No records with an exclusive product or core-brand target.')
        else:
            st.vega_lite_chart(comparison, {
                'mark': {'type': 'bar', 'tooltip': True},
                'encoding': {'x': {'field': 'target', 'type': 'nominal', 'title': 'Exclusive target'},
                             'y': {'field': 'Records', 'type': 'quantitative'},
                             'color': {'field': 'sentiment', 'type': 'nominal', 'scale': {
                                 'domain': ['positive', 'negative', 'neutral', 'mixed'],
                                 'range': ['#171717', '#C62430', '#BFBFBF', '#747474']}}}})
        st.caption('“Both” and unclear targets are omitted: one overall sentiment cannot be assigned separately to multiple targets.')
    with cols[1]:
        st.markdown('#### Attribution of responsibility')
        counts = breakdown(rows, 'responsibility')
        st.bar_chart(counts, x='responsibility', y='Records', color='#C62430')
    st.markdown('#### Spillover by year and source')
    trends = spillover_trends(rows)
    if trends.empty:
        st.info('No dated records for trends. Synthetic fixtures have no invented publication dates.')
    else:
        st.vega_lite_chart(trends, {
            'mark': {'type': 'bar', 'tooltip': True},
            'encoding': {'x': {'field': 'year', 'type': 'ordinal', 'title': 'Publication year'},
                         'y': {'field': 'Records', 'type': 'quantitative'},
                         'color': {'field': 'spillover', 'type': 'nominal', 'scale': {
                             'domain': ['explicit', 'implicit', 'none', 'unclear'],
                             'range': ['#C62430', '#747474', '#171717', '#BFBFBF']}},
                         'column': {'field': 'source', 'type': 'nominal'}}})
        st.dataframe(trends, hide_index=True)
    with st.expander('Inspect the records behind these counts'):
        st.dataframe(pd.DataFrame([dict(record_id=row['record_id'], source=row['source'],
                     published_at=row['published_at'], **{k: row['active_labels'][k] for k in LABELS}) for row in rows]), hide_index=True)


def prediction_detail(row, demo):
    st.caption(f"{row['source']} · {row.get('published_at') or 'Publication date unavailable'} · {row['record_id']}")
    if row.get('url') and row['url'].startswith(('https://', 'http://')):
        st.link_button('Open original source', row['url'])
    st.markdown('<div class="evidence-text">' + highlighted_evidence(row['text'], row['prediction']['evidence_quotes']) + '</div>', unsafe_allow_html=True)
    st.caption('Highlighted quotations are from the AI prediction.' if not demo else 'Highlighted quotations are from the synthetic fixture reference.')
    cols = st.columns(2)
    with cols[0]:
        st.markdown('#### Fixture reference — not AI' if demo else '#### Original AI prediction')
        st.json(row['prediction'])
    with cols[1]:
        st.markdown('#### Human labels' if not demo else '#### Demo reviewer labels — session only')
        if row['human_labels'] is None:
            st.info('Not reviewed.')
        else:
            st.json(row['human_labels'])
    st.caption(f"Model: {row['model_name']} · Version: {row['model_version']} · Prompt: {row['prompt_version']}")


def explorer_panel(rows, demo):
    st.subheader('Every conclusion has a source')
    if not rows:
        st.info('No classified customer discussions are available. No empty search or label filters are shown.')
        return
    basis = st.radio('Explorer label basis', ['AI predictions', 'Human-reviewed labels'], horizontal=True,
                     format_func=lambda value: 'Fixture references (not AI)' if demo and value == 'AI predictions' else value,
                     key=f'voice_basis_{demo}')
    selected = select_label_basis(rows, basis)
    if not selected:
        st.info('No records are available for this label basis. Human-reviewed labels require a separate saved review.')
        return
    search = st.text_input('Search original discussion text', key=f'voice_search_{demo}')
    cols = st.columns(4)
    sentiments = cols[0].multiselect('Sentiment', LABELS['sentiment'], key=f'voice_sentiment_{demo}')
    topics = cols[1].multiselect('Topic (any match)', TOPICS, key=f'voice_topic_{demo}')
    targets = cols[2].multiselect('Target', LABELS['target'], key=f'voice_target_{demo}')
    spillovers = cols[3].multiselect('Spillover', LABELS['spillover'], key=f'voice_spillover_{demo}')
    review_only = st.checkbox('Only flagged, unreviewed records', key=f'voice_flagged_{demo}')
    selected = filter_discussions(selected, search=search, sentiments=sentiments, topics=topics,
                                   targets=targets, spillovers=spillovers, review_only=review_only)
    st.caption(f'{len(selected)} records match. Confidence is uncalibrated; AI labels are predictions, not verified findings.')
    if not selected:
        st.info('No classified discussions match. Try demo mode or classify permitted customer records.')
        return
    st.dataframe(pd.DataFrame([dict(record_id=row['record_id'], source=row['source'],
                  published_at=row['published_at'], text=row['text'],
                  **{k: row['active_labels'][k] for k in LABELS}, topic=', '.join(row['active_labels']['topic']),
                  confidence=row['active_labels']['confidence'], needs_review=row['needs_review']) for row in selected]), hide_index=True)
    by_id = {row['record_id']: row for row in selected}
    record_id = st.selectbox('Inspect a prediction', list(by_id), key=f'voice_record_{demo}')
    prediction_detail(by_id[record_id], demo)


def evaluation_panel(rows, demo):
    st.markdown('#### Explicit spillover validation')
    if not rows or not any(row['human_labels'] is not None for row in rows):
        st.info('No reviewed predictions are available for validation metrics or a confusion matrix.')
        return
    if demo:
        pairs = [(row['prediction'], row['human_labels']) for row in rows if row['human_labels'] is not None]
        metrics = evaluate_pairs(pairs)
        st.caption('DEMO agreement with fixture references, not AI performance or research accuracy.')
    else:
        metrics = evaluate_research()
        st.caption('AI predictions versus latest human labels, one latest eligible run per real record. '
                   'Review selection may be biased; this is not a held-out benchmark.')
    binary = metrics['explicit_spillover']
    reliable = metrics['n'] >= MIN_SAMPLE and binary['support'] >= 5
    cols = st.columns(4)
    for col, field in zip(cols, ['accuracy', 'precision', 'recall', 'f1']):
        value = binary[field]
        display = 'Insufficient validation' if not reliable else ('Undefined' if value is None else f'{value:.2f}')
        col.metric(field.title(), display)
    st.caption(f"Reviewed n={metrics['n']} · Human explicit-spillover positives={binary['support']}. "
               f"Headline scores require n≥{MIN_SAMPLE} and ≥5 explicit positives. These are display safeguards, not statistical guarantees.")
    matrix = pd.DataFrame([[binary['tp'], binary['fn']], [binary['fp'], binary['tn']]],
                          index=['Human: explicit', 'Human: other'], columns=['AI: explicit', 'AI: other'])
    if demo:
        matrix.columns = ['Fixture: explicit', 'Fixture: other']
    st.dataframe(matrix)
    with st.expander('Inspect descriptive metrics, denominators and label-level results'):
        st.caption('Small-sample values are descriptive only. Undefined ratios are null.')
        st.json(metrics)


def validation_panel(rows, demo):
    st.subheader('Human judgment, preserved separately')
    evaluation_panel(rows, demo)
    if not rows:
        st.info('No eligible predictions to review yet.')
        return
    ordered = sorted(rows, key=lambda row: (row['human_labels'] is not None, row['prediction']['spillover'] != 'explicit', row['prediction']['confidence']))
    by_id = {row['record_id']: row for row in ordered}
    record_id = st.selectbox('Record for human review', list(by_id), key=f'review_record_{demo}')
    row = by_id[record_id]
    prediction_detail(row, demo)
    label = row['human_labels'] or row['prediction']
    with st.form(f"review_form_{demo}_{row['attempt_id']}_{row['review_id']}"):
        st.caption('Correct or confirm the complete label set. Evidence must remain exact quotations from the original text.')
        if demo:
            st.caption('Use an invented reviewer alias and synthetic-only notes. Do not enter personal or research information.')
        cols = st.columns(2)
        correction = {}
        for index, (field, options) in enumerate(LABELS.items()):
            correction[field] = cols[index % 2].selectbox(field.replace('_', ' ').title(), options, index=options.index(label[field]))
        correction['topic'] = st.multiselect('Topics', TOPICS, default=label['topic'])
        correction['confidence'] = st.number_input('Reviewer confidence (0–1)', 0.0, 1.0, float(label['confidence']), 0.05)
        correction['rationale'] = st.text_area('Classification rationale', label['rationale'])
        evidence = st.text_area('Evidence quotations (JSON array)', json.dumps(label['evidence_quotes'], ensure_ascii=False, indent=2))
        reviewer = st.text_input('Reviewer identifier')
        reason = st.text_input('Reason for correction or confirmation')
        submit = st.form_submit_button('Save human review', type='primary')
    if submit:
        try:
            correction['evidence_quotes'] = json.loads(evidence)
            validated = validate_labels(correction, row['text'])
            if not reviewer.strip() or not reason.strip():
                raise ValueError('Reviewer identifier and review reason are required.')
            if demo:
                reviews = st.session_state.setdefault('contagion_demo_reviews', {})
                history = reviews.setdefault(record_id, [])
                history.append(dict(labels=validated, reviewer=reviewer, reason=reason))
            else:
                append_review(row['attempt_id'], validated, reviewer, reason)
            st.session_state['contagion_review_saved'] = True
            st.rerun()
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))
    with st.expander('Append-only prediction and review history'):
        if demo:
            st.json(st.session_state.get('contagion_demo_reviews', {}).get(record_id, []))
        else:
            history = get_history(record_id)
            for name in ('attempts', 'reviews'):
                st.markdown(f'**{name.title()}**')
                if history[name]:
                    st.dataframe(pd.DataFrame(history[name]), hide_index=True)


def render_contagion(*, force_demo=False):
    st.markdown('''<style>
        .block-container {max-width:1400px; padding-top:2.4rem;}
        h1 {letter-spacing:-.045em;} h2,h3 {letter-spacing:-.025em;}
        [data-testid="stMetric"] {border-top:2px solid #C62430; padding:1rem 0;}
        .evidence-text {white-space:pre-wrap; line-height:1.8; padding:1.2rem;
            border-left:3px solid #C62430; background:#F5F5F5; border-radius:4px;}
        mark {background:#F7D9DC; color:#171717; padding:.1em .15em;}
        .story-card {height:100%; border:1px solid #E3E3E3; border-top:3px solid;
            border-radius:6px; padding:1.3rem; margin-bottom:1rem;}
        .story-card h3 {font-size:1.25rem; margin:.6rem 0; line-height:1.25;}
        .story-card p {font-size:.96rem; line-height:1.6;}
        .story-kicker {font-size:.72rem; font-weight:700; letter-spacing:.1em; color:#666;}
        .story-card blockquote {margin:1rem 0 .5rem; padding-left:.8rem;
            border-left:2px solid #C62430; font-size:.95rem; line-height:1.6;}
        .story-card small {font-size:.78rem; color:#606060;}
        .story-process {display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);
            align-items:start; gap:.65rem; margin:1.5rem 0;}
        .process-step {background:#F5F5F5; padding:1rem; border-radius:5px; min-width:0; overflow-wrap:break-word;}
        .process-step strong {display:block; font-size:1rem; line-height:1.4; margin:.5rem 0;}
        .process-step small {font-size:.65rem; font-weight:700; letter-spacing:.05em; color:#666;}
        .process-step p {font-size:.85rem; line-height:1.5; margin-bottom:0;}
        .process-arrow {color:#C62430; padding-top:2.5rem;}
        @media(max-width:800px) {
            .story-process {grid-template-columns:1fr; gap:.4rem;}
            .process-arrow {padding:0; text-align:center; transform:rotate(90deg);}
            .block-container {padding:1.2rem 1rem;}
            h1 {font-size:2rem !important; line-height:1.15 !important;}
            [data-testid="stTabs"] [role="tablist"] {gap:.5rem; flex-wrap:wrap; height:auto;}
            [data-testid="stTabs"] [role="tab"] {white-space:normal; height:auto; min-height:2.6rem;}
        }
        </style>''', unsafe_allow_html=True)
    with st.sidebar:
        st.markdown('### RAY-BAN')
        st.caption('CUSTOMER TRUST INTELLIGENCE')
        st.divider()
        st.caption('HEC Paris · Strategic Management\n\nEvidence period 2023–2026 · Horizon 2030')
        if force_demo:
            st.caption('PUBLIC DEMO · Research operations are unavailable.')
            mode = 'Synthetic demo'
        else:
            mode = st.radio('Analysis mode', ['Research', 'Synthetic demo'], key='contagion_mode')
        if st.button('Refresh analysis'):
            st.rerun()
    demo = mode == 'Synthetic demo'
    st.caption('CUSTOMER VOICE / PRODUCT → BRAND')
    if force_demo:
        from src.ui.strategic_story import QUESTION
        st.title(QUESTION)
        st.caption('HEC Paris · Market Convergence & Legitimacy · Strategic horizon 2030')
    else:
        st.title('Brand Contagion Analysis')
        st.write('Distinguish criticism of smart glasses from distrust of the wider Ray-Ban brand.')
    if force_demo:
        from src.ui.synthetic_reactions import render_public_dashboard
        render_public_dashboard()
        return
    if demo:
        st.warning('SYNTHETIC DEMONSTRATION · Customer scenarios are invented; the timeline uses sourced real-world events. '
                   'Fixture labels and actual recorded local AI outputs are shown separately. No customer research findings. '
                   'Demo reviews are session-only and never enter SQLite.')
        rows = demo_discussions()
        from src.ui.demo_benchmark import render_benchmark
        with st.expander('Previous fixed-set AI benchmarks — separate v1/v2 diagnostics'):
            render_benchmark()
        for row in rows:
            reviews = st.session_state.get('contagion_demo_reviews', {}).get(row['record_id'], [])
            if reviews:
                row['human_labels'] = reviews[-1]['labels']
                row['review_id'] = len(reviews)
    else:
        rows = classified_discussions()
        st.caption('Permission-verified customer discussions only. News and synthetic records never contribute to research analytics.')
    if st.session_state.pop('contagion_review_saved', False):
        st.success('Human review saved separately; the original prediction is unchanged.')
    result = st.session_state.pop('contagion_result', None)
    if result:
        st.dataframe(pd.DataFrame(result).drop(columns=['labels'], errors='ignore'), hide_index=True)
    tabs = st.tabs(['Contagion analytics', 'Customer voice', 'Local classification', 'Human validation',
                    'Verified timeline', 'Synthetic AI case study', 'Strategic implications', 'Real Media Evidence'])
    with tabs[0]:
        if demo:
            from src.ui.synthetic_reactions import render_simulation
            render_simulation()
            with st.expander('Legacy small-fixture sandbox — separate from the generated scenarios'):
                analytics_panel(rows, demo)
        else:
            analytics_panel(rows, demo)
    with tabs[1]:
        if demo:
            st.caption('This is the separate small-fixture sandbox. The generated customer-reaction corpus and its filters are in Contagion analytics.')
        explorer_panel(rows, demo)
    with tabs[2]:
        classification_panel(demo)
    with tabs[3]:
        validation_panel(rows, demo)
    from src.ui.research_evidence import render_timeline, render_case_study, render_strategy
    with tabs[4]:
        render_timeline()
    with tabs[5]:
        render_case_study()
    with tabs[6]:
        render_strategy()
    with tabs[7]:
        if force_demo:
            from src.ui.synthetic_reactions import render_public_sources
            render_public_sources()
        else:
            from src.ui.media_evidence import render_real_media
            render_real_media(allow_review=True)
