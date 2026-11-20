"""Read-only public synthetic demonstration; no credentials, network or database access."""
from collections import Counter
import json
from pathlib import Path

from src.analysis.simulation import (NOTICE, fingerprint, validate_sources, validate_scenarios,
    scenario_distributions, filter_scenarios, evaluate_simulation, display_basis, representative_case)
from src.analysis.schema import LABELS
from src.analysis.schema import validate_labels
from src.analysis.evaluation import evaluate_pairs

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_RELEASE = 'hec-review-2026-11-20-v1'


def read(name):
    return json.loads((ROOT / 'demo' / name).read_text(encoding='utf-8'))


def load_public_sources():
    report = read('media_sources.json')
    if report.get('kind') != 'public_bibliographic_context_not_customer_data':
        raise ValueError('Public source manifest must contain bibliographic context only.')
    validate_sources(report['sources'])
    if report['sha256'] != fingerprint(report['sources']):
        raise ValueError('Public source manifest changed.')
    return report


def load_simulation():
    if not (ROOT / 'demo/grounded_scenarios.json').exists():
        return None, None, None
    dataset = read('grounded_scenarios.json')
    manifest = load_public_sources()
    timeline = read('research_timeline.json')
    if dataset['timeline_sha256'] != fingerprint(timeline['events']):
        raise ValueError('Simulation timeline provenance mismatch.')
    validate_scenarios(dataset, manifest['sources'], timeline['events'], complete=dataset.get('completed') is True)
    if dataset.get('completed') and dataset['records_sha256'] != fingerprint(dataset['records']):
        raise ValueError('Scenario dataset fingerprint mismatch.')
    output = read('simulation_classifications.json') if (ROOT / 'demo/simulation_classifications.json').exists() else None
    if output is not None:
        if output.get('synthetic_only') is not True or output.get('notice') != NOTICE or output['records_sha256'] != fingerprint(dataset['records']):
            raise ValueError('Model outputs must refer only to these frozen synthetic scenarios.')
        by_id = {row['synthetic_id']: row for row in dataset['records']}
        seen = set()
        for result in output['results']:
            if result['case'] not in by_id or result['case'] in seen or result['reference'] != by_id[result['case']]['expected_labels']:
                raise ValueError('Model output/reference mismatch or duplicate inference result.')
            seen.add(result['case'])
            try:
                parsed = json.loads(result['raw_output'])
            except (ValueError, TypeError):
                parsed = None
            if parsed != result.get('parsed_output'):
                raise ValueError('Stored parsed response differs from raw output.')
            try:
                evaluate_pairs([(parsed, result['reference'])])
                evaluable = True
            except (ValueError, TypeError, KeyError, AttributeError):
                evaluable = False
            if evaluable != result['label_fields_evaluable']:
                raise ValueError('Raw output evaluability flag is inconsistent.')
            try:
                validate_labels(result['raw_output'], by_id[result['case']]['text'])
                valid = True
            except (ValueError, TypeError, KeyError):
                valid = False
            if result['status'] not in ('success', 'failed') or valid != (result['status'] == 'success'):
                raise ValueError('Saved safeguard outcome differs from replayed validation.')
        if output.get('completed') and len(seen) != len(by_id):
            raise ValueError('Completed classification run is missing scenarios.')
        if output['summary'] != evaluate_simulation(output['results']):
            raise ValueError('Saved evaluation does not match recorded predictions.')
    return dataset, output, manifest


def load_review_proposals():
    report = read('classification_review_proposals.json')
    if report.get('kind') != 'ai_assisted_review_proposals_not_human_validation' or report.get('is_synthetic') is not True:
        raise ValueError('Review proposals must not be presented as human validation.')
    for filename, field, key in (('grounded_scenarios.json','records','dataset_sha256'), ('simulation_classifications.json','results','predictions_sha256')):
        if fingerprint(read(filename)[field]) != report[key]:
            raise ValueError('Review proposals refer to changed historical artefacts.')
    if len(report['records']) != 50 or fingerprint(report['records']) != report['records_sha256']:
        raise ValueError('Expected the frozen stratified 50-case proposal review.')
    dataset = {r['synthetic_id']:r for r in read('grounded_scenarios.json')['records']}
    for row in report['records']:
        if row['text'] != dataset[row['synthetic_id']]['text'] or any(q not in row['text'] for q in row['evidence_quotes']):
            raise ValueError('Review evidence must match the original synthetic text exactly.')
        if row['review_status'] != 'AI-assisted proposal — pending independent human validation':
            raise ValueError('No review proposal is an independent human approval.')
    return report


def render_public_sources():
    import pandas as pd
    import streamlit as st

    st.subheader('Real Media Evidence')
    st.caption('Genuine bibliographic context, separate from invented reactions and model evaluation. '
               'No customer opinions, private research files or named human reviews are loaded here.')
    try:
        report = load_public_sources()
    except (FileNotFoundError, ValueError, KeyError) as exc:
        st.info(f'Public bibliographic context is unavailable: {exc}')
        return
    frame = pd.DataFrame(report['sources'])
    st.metric('Genuine source references', len(frame))
    st.write('Source mix: ' + ', '.join(f'{count} {category.replace("_", " ")}' for category, count in Counter(frame['source_category']).items()))
    st.caption(report['verification'] + ' Article bodies and customer comments are not included. '
               'Allegations and inquiries do not establish liability. Media naming does not establish brand damage.')
    st.dataframe(frame[['published_at', 'publisher', 'title', 'url', 'source_category', 'evidence_type', 'source_id']],
                 hide_index=True, column_config={'url': st.column_config.LinkColumn('Original source')})


def render_simulation(*, include_details=True):
    import pandas as pd
    import streamlit as st

    st.subheader('Grounded customer reaction simulations')
    st.warning(NOTICE)
    try:
        dataset, output, manifest = load_simulation()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f'Synthetic artefacts failed provenance checks: {exc}')
        return
    if dataset is None:
        st.info('No generated scenarios are available. No generation or inference runs on refresh.')
        return
    rows = dataset['records']
    if not dataset.get('completed'):
        st.info(f'Generation is incomplete: {len(rows)} recorded scenarios. No completion is implied.')
    st.caption('The scenario quotas deliberately over-sample privacy criticism and wider-brand distrust. '
               'Choose the label basis explicitly: design intentions or accepted local AI predictions. Neither is population sentiment. '
               'Simulated dates provide narrative context, not historical customer trends.')
    basis = st.radio('Synthetic chart label basis', ['Scenario design references', 'Accepted local AI predictions'],
                     key='simulation_basis', horizontal=True)
    use_ai = basis == 'Accepted local AI predictions'
    if use_ai:
        if output is None:
            st.info('No recorded model predictions yet. Choose scenario design references to inspect the generated text.')
            chart_rows = []
        else:
            chart_rows = display_basis(rows, output['results'])
            st.caption(f"Accepted-only chart sample: {len(chart_rows)}/{len(rows)} scenarios. Rejected/unattempted cases are omitted, never filled with design labels.")
            if output.get('completed') and not output['summary']['accepted_prediction_distributions']['spillover'].get('explicit', 0):
                st.info('No explicit-spillover prediction passed the safeguards in this saved run. '
                        'This exposes a model/reference-agreement limitation; it does not establish absence of real brand spillover.')
    else:
        chart_rows = display_basis(rows)
        st.caption('Design-reference charts describe intended scenarios, not validated semantic annotations or model predictions.')
    with st.expander('Scenario design and generation provenance'):
        st.json({key: dataset[key] for key in ('category_quotas', 'reference_basis', 'generation_model',
                                               'generation_prompt_sha256', 'plan_sha256')})
        if dataset.get('quality'):
            diversity = dataset['quality']['diversity']
            st.caption(f"Diversity audit: {dataset['quality']['unique_normalized_texts']} unique normalized texts; "
                       f"{diversity['min_words']}–{diversity['max_words']} words; "
                       f"{len(diversity['high_similarity_pairs'])} similar-wording pairs flagged. "
                       'Repeated structures remain; lexical checks are not human validation.')
    columns = st.columns(4)
    years = columns[0].multiselect('Simulated year', sorted({row['simulated_publication_year'] for row in rows}), key='simulation_years')
    sentiments = columns[1].multiselect('Scenario sentiment', LABELS['sentiment'], key='simulation_sentiments')
    responsibilities = columns[2].multiselect('Scenario responsibility', LABELS['responsibility'], key='simulation_responsibilities')
    spillovers = columns[3].multiselect('Scenario spillover', LABELS['spillover'], key='simulation_spillovers')
    selected = filter_scenarios(chart_rows, years=years, sentiments=sentiments, responsibilities=responsibilities,
                                spillovers=spillovers, label_key='active_labels')
    counters = st.columns(4)
    counters[0].metric('Visible simulated reactions', f'{len(selected)}/{len(rows)}')
    counters[1].metric('Simulated product-only criticism', sum(r['scenario_category'] == 'privacy_product_criticism' for r in selected))
    counters[2].metric('Simulated wider-brand distrust', sum(r['scenario_category'] == 'wider_brand_distrust' for r in selected))
    counters[3].metric('Linked genuine source articles', len({s for r in selected for s in r['related_article_ids']}))
    st.caption(NOTICE)
    if not selected:
        st.info('No scenarios match these filters. Clear a filter to restore the demonstration.')
    else:
        distributions = scenario_distributions(selected, label_key='active_labels')
        columns = st.columns(2)
        for index, (field, title) in enumerate((('sentiment', 'Simulated sentiment'), ('spillover', 'Simulated brand spillover'),
                                               ('responsibility', 'Simulated responsibility attribution'), ('purchase_intent', 'Simulated purchase intention'))):
            with columns[index % 2]:
                st.write('**' + title + '**')
                st.caption(NOTICE + ' Label basis: ' + basis + '.')
                st.bar_chart(pd.DataFrame.from_dict(distributions[field], orient='index', columns=['Simulated reaction count']), color='#C62430')
        st.write('**Product criticism versus wider-brand distrust**')
        st.caption(NOTICE + ' Counts reflect assigned scenario categories; no causal effect is estimated.')
        st.bar_chart(pd.DataFrame.from_dict(dict(Counter(r['scenario_category'] for r in selected)), orient='index', columns=['Designed scenario count']), color='#C62430')
        if include_details:
            _render_voice(selected, output, manifest)
    with st.expander('H1, H2 and H3: contrasting illustrative mechanisms', expanded=True):
        st.caption(NOTICE + ' These examples illustrate hypotheses; they do not test them empirically.')
        for hypothesis, category, explanation in (
            ('H1', 'privacy_product_criticism', 'Concern remains attached to the camera/AI product.'),
            ('H2', 'wider_brand_distrust', 'A customer could transfer distrust when Ray-Ban endorsement makes the partnership feel like a breach of wider-brand values.'),
            ('H3', 'meta_responsibility_brand_protected', 'Assigning the data-processing role to Meta can preserve a boundary around traditional eyewear.')):
            example = representative_case(selected, category)
            st.write(f'**{hypothesis}: {explanation}**')
            if example:
                st.write(f"{example['synthetic_id']} — SIMULATED: {example['text']}")
            else:
                st.caption('No matching scenario in the current filtered subset.')
    if include_details:
        with st.expander('Local AI agreement against synthetic references'):
            _render_evaluation(dataset, output)
    csv_path = ROOT / 'demo/grounded_scenarios.csv'
    if dataset.get('completed') and csv_path.exists():
        st.download_button('Download labelled synthetic scenario CSV', csv_path.read_bytes(),
                           'AI_GENERATED_SIMULATIONS.csv', 'text/csv')


def _render_voice(selected, output, manifest, *, inspect_key="simulation_inspect"):
    import pandas as pd
    import streamlit as st
    if not selected:
        st.info("No scenarios match these filters.")
        return
    predictions = {r['case']:r for r in output['results']} if output else {}
    compact = [dict(synthetic_id=r['synthetic_id'], simulated_year=r['simulated_publication_year'],
                    text=r['text'], **{k: v for k, v in r['active_labels'].items() if k in LABELS},
                    design_spillover=r['expected_labels']['spillover'],
                    raw_AI_spillover=(predictions.get(r['synthetic_id'],{}).get('parsed_output') or {}).get('spillover'),
                    historical_status=predictions.get(r['synthetic_id'],{}).get('status','unattempted')) for r in selected]
    st.caption('Raw AI columns can contain rejected outputs. Historical status controls acceptance; design labels never replace a failed prediction.')
    st.dataframe(pd.DataFrame(compact), hide_index=True)
    selected_id = st.selectbox('Inspect an AI-generated reaction', [r['synthetic_id'] for r in selected], key=inspect_key)
    row = next(r for r in selected if r['synthetic_id'] == selected_id)
    st.info('SIMULATED CUSTOMER — ' + row['text'])
    st.caption(f"Simulated date: {row['simulated_publication_date']} · {row['scenario_category']} · {row['writing_style']}")
    st.json({'scenario_design_reference_not_ground_truth': row['expected_labels']})
    for source_id in row['related_article_ids']:
        source = next(s for s in manifest['sources'] if s['source_id'] == source_id)
        st.link_button(f"Context: {source['publisher']} · {source['published_at']} · {source['title']}", source['url'])
    if output:
        prediction = next((r for r in output['results'] if r['case'] == selected_id), None)
        if prediction:
            st.write('**Actual local model response — ' + prediction['status'] + '**')
            st.code(prediction['raw_output'] or '(No model output)', language='json')
            st.caption(prediction.get('validation') or prediction.get('error') or 'No validation detail recorded.')
    proposal_file = ROOT / 'demo/classification_review_proposals.json'
    if proposal_file.exists():
        proposal = next((r for r in load_review_proposals()['records'] if r['synthetic_id']==selected_id), None)
        if proposal:
            with st.expander('AI-assisted review proposal — not independent human validation'):
                st.json(proposal['proposed_labels'])
                st.write(proposal['proposal_rationale'])
                st.text('Supporting original text: ' + proposal['evidence_quotes'][0])
                st.caption(proposal['review_status'])


def _render_evaluation(dataset, output):
    import pandas as pd
    import streamlit as st
    rows = dataset["records"]
    st.caption('Evaluation uses the full frozen dataset and is unaffected by scenario filters. '
               'Reference labels were supplied to the same model during generation. This is circular, '
               'in-sample diagnostic agreement, not independently validated accuracy or evidence of customer views. '
               'Raw scores include evaluable rejected responses; accepted-only scores use a selected subset. '
               'Rejected predictions are abstentions and never silently become none.')
    if output is None:
        st.info('No recorded classification outputs yet. No inference runs automatically.')
    else:
        summary = output['summary']
        st.write(f"Recorded {summary['n']}/{len(rows)} · accepted {summary['accepted']} · rejected {summary['rejected']} · evaluable raw {summary['evaluable']}.")
        if not output.get('completed'):
            st.warning('Partial inference run. Scores below cover only completed attempts.')
        records = []
        for basis in ('raw_metrics', 'accepted_metrics'):
            metrics = summary[basis]
            for field, score in metrics['fields'].items():
                explicit = metrics['explicit_spillover'] if field == 'spillover' else {}
                records.append(dict(basis=basis, field=field, n=metrics['n'], accuracy=score['accuracy'],
                    explicit_precision=explicit.get('precision'), explicit_recall=explicit.get('recall'), explicit_f1=explicit.get('f1')))
        st.dataframe(pd.DataFrame(records), hide_index=True)
        field = st.selectbox('Synthetic evaluation confusion matrix', list(LABELS), key='simulation_confusion')
        st.caption('Rows: scenario design reference. Columns: raw evaluable model prediction. No held-out customer data.')
        st.dataframe(pd.DataFrame(summary['raw_metrics']['fields'][field]['confusion']).T, hide_index=False)
        st.json({key: summary[key] for key in ('false_positives', 'false_negatives', 'rejected_reference_positives', 'mean_seconds')})
        st.write('Actual accepted-model label counts, distinct from the designed scenario distributions:')
        st.json(summary['accepted_prediction_distributions'])
        st.json({'model': output['model'], 'classification_prompt': output['prompt_version'], 'prompt_sha256': output['prompt_sha256']})


def render_customer_voice():
    import streamlit as st
    st.subheader('Interactive customer voice — AI-generated simulations')
    st.caption(NOTICE)
    dataset, output, manifest = load_simulation()
    if dataset is None:
        st.info('No public scenario dataset is available.')
        return
    basis = st.radio('Customer voice filter basis', ['Scenario design references','Accepted local AI predictions'],
                     key='public_voice_basis', horizontal=True)
    rows = display_basis(dataset['records'], output['results'] if output and basis.startswith('Accepted') else None)
    cols = st.columns(4)
    years = cols[0].multiselect('Voice: simulated year', sorted({r['simulated_publication_year'] for r in dataset['records']}), key='public_voice_years')
    sentiments = cols[1].multiselect('Voice: sentiment', LABELS['sentiment'], key='public_voice_sentiments')
    responsibilities = cols[2].multiselect('Voice: responsibility', LABELS['responsibility'], key='public_voice_responsibilities')
    spillovers = cols[3].multiselect('Voice: spillover', LABELS['spillover'], key='public_voice_spillovers')
    status = st.selectbox('Prediction review queue', ['All scenarios','Rejected predictions','Uncertain or needs review'], key='public_voice_status')
    selected = filter_scenarios(rows, years=years, sentiments=sentiments, responsibilities=responsibilities,
                                spillovers=spillovers, label_key='active_labels')
    by_id = {r['case']:r for r in output['results']} if output else {}
    if status == 'Rejected predictions':
        selected = [r for r in selected if by_id.get(r['synthetic_id'],{}).get('status')=='failed']
    elif status == 'Uncertain or needs review':
        selected = [r for r in selected if by_id.get(r['synthetic_id'],{}).get('needs_review')]
    st.write(f"Showing {len(selected)}/{len(dataset['records'])} simulations. Filter basis: {basis}.")
    st.caption('Use design-reference mode to inspect rejected cases. Accepted-AI mode omits rejections; it never substitutes reference labels.')
    _render_voice(selected, output, manifest, inspect_key='public_voice_inspect')


def render_review_proposals():
    import pandas as pd
    import streamlit as st
    report = load_review_proposals()
    st.subheader('50-case AI-assisted error review')
    st.warning('AI-assisted editorial proposals, not independent human validation. Original labels, model outputs and the 220/40 historical split are unchanged.')
    st.write('Sample: all 30 designed explicit cases, 10 product/Meta criticism cases, and 10 implicit/brand-protection cases.')
    st.write('Among the 30 designed explicit cases, the proposed review labels are: ' +
             ', '.join(f'{n} {label}' for label,n in report['summary']['designed_explicit_proposals'].items()) + '.')
    st.caption('These proposed counts are not a new benchmark or estimates of actual customer sentiment.')
    st.dataframe(pd.DataFrame([dict(synthetic_id=r['synthetic_id'], stratum=r['stratum'],
        designed_spillover=r['original_design_labels']['spillover'],
        raw_AI_spillover=r['historical_prediction']['spillover'], historical_status=r['historical_status'],
        proposed_spillover=r['proposed_labels']['spillover'], proposal_rationale=r['proposal_rationale'],
        review_status=r['review_status']) for r in report['records']]), hide_index=True)
    st.download_button('Download 50 review proposals (not human labels)',
        (ROOT/'demo/classification_review_proposals.csv').read_bytes(), 'AI_ASSISTED_REVIEW_PROPOSALS.csv','text/csv')


def render_public_dashboard():
    import streamlit as st
    dataset, output, manifest = load_simulation()
    st.caption('PUBLIC RELEASE · ' + PUBLIC_RELEASE)
    st.warning('SYNTHETIC DEMONSTRATION · ' + NOTICE)
    if dataset is None or output is None:
        st.error('The public demonstration assets are unavailable. No substitute findings are generated.')
        return
    cols=st.columns(4)
    for col,label,value in zip(cols, ('Simulated customer reactions','Contextual news sources',
                                      'Accepted model classifications','Rejected model classifications'),
                               (len(dataset['records']),len(manifest['sources']),output['summary']['accepted'],output['summary']['rejected'])):
        col.metric(label,value)
    st.write('**When could criticism of smart glasses reach ordinary Ray-Ban eyewear?** '
             'Explore product-specific concern (H1), perceived endorsement and wider distrust (H2), '
             'and insulation when responsibility stays with Meta (H3). These are illustrative mechanisms, not measured brand damage.')
    tabs=st.tabs(['Contagion analytics','Customer voice','Verified timeline','Strategic implications','Model evaluation','Real Media Evidence'])
    with tabs[0]:
        render_simulation(include_details=False)
    with tabs[1]:
        render_customer_voice()
    from src.ui.research_evidence import render_timeline, render_strategy, render_case_study
    with tabs[2]:
        render_timeline()
    with tabs[3]:
        render_strategy()
    with tabs[4]:
        st.subheader('Model evaluation — saved local Qwen outputs')
        st.write('Historical run: 260 attempts, 220 accepted, 40 rejected. Raw spillover agreement is 52.3% against unvalidated scenario-design labels. No explicit-spillover output passed the historical safeguards.')
        _render_evaluation(dataset, output)
        render_review_proposals()
    with tabs[5]:
        render_public_sources()
    with st.expander('Advanced: historical benchmarks and small-fixture sandbox'):
        from src.ui.demo_benchmark import render_benchmark
        from src.ui.contagion_data import demo_discussions
        from src.ui.contagion import analytics_panel, explorer_panel, classification_panel, validation_panel
        render_benchmark()
        st.caption('The following legacy fixtures are separate from the 260 generated scenarios. Demo corrections remain session-only.')
        rows=demo_discussions()
        for row in rows:
            reviews=st.session_state.get('contagion_demo_reviews',{}).get(row['record_id'],[])
            if reviews:
                row['human_labels']=reviews[-1]['labels'];row['review_id']=len(reviews)
        analytics_panel(rows,True)
        explorer_panel(rows,True)
        classification_panel(True)
        validation_panel(rows,True)
        render_case_study()
