"""Presentation of frozen evidence and scenarios; no inference or data mutation."""
from html import escape

QUESTION = "Can Meta's Privacy Scandals Damage the Ray-Ban Brand?"
CONCLUSION = ('Brand contagion is a plausible strategic risk, '
              'but actual wider-brand damage has not been established.')
SECTIONS = ['Strategic Question', 'Evidence & Methodology', 'Analysis',
            'Insights & Synthesis', 'Research Appendix']
LABEL_BASIS_GUIDE = (
    'Explore four dimensions: sentiment (tone), responsibility (who is blamed), '
    'brand spillover (whether distrust reaches traditional Ray-Ban), and purchase intention. '
    'Start with Scenario design references to explore all 260 constructed reactions; these labels '
    'describe the intended scenarios, not validated ground truth. Accepted local AI predictions '
    'uses the 220 predictions that passed safeguards and excludes the 40 rejected outputs. '
    'Neither option measures real customer sentiment.'
)
NAMES = {
    'explicit': 'Explicit wider-brand distrust', 'implicit': 'Implicit brand association',
    'none': 'No spillover', 'unclear': 'Unclear / not stated',
    'Meta': 'Meta', 'Ray-Ban': 'Ray-Ban', 'both': 'Both partners',
    'positive': 'Positive', 'negative': 'Negative', 'neutral': 'Neutral', 'mixed': 'Mixed',
    'privacy_product_criticism': 'Product privacy criticism',
    'wider_brand_distrust': 'Designed wider-brand distrust',
    'meta_responsibility_brand_protected': 'Meta blamed; Ray-Ban protected',
    'positive_experience': 'Positive experience', 'neutral_or_mixed': 'Neutral or mixed reaction',
    'Ray-Ban Meta': 'Ray-Ban Meta', 'core Ray-Ban': 'Traditional Ray-Ban',
}


def readable(value):
    return NAMES.get(value, value.replace('_', ' ').capitalize())


def card(kicker, title, text, *, accent='#171717', extra=''):
    import streamlit as st
    st.markdown(f'<article class="story-card" style="border-top-color:{accent}">'
                f'<div class="story-kicker">{escape(kicker)}</div><h3>{escape(title)}</h3>'
                f'<p>{escape(text)}</p>{extra}</article>', unsafe_allow_html=True)


def render_mechanisms(records):
    import streamlit as st
    by_id = {r['synthetic_id']: r for r in records}
    st.subheader('Three ways the brand boundary could behave')
    st.caption('Three possible customer reactions, illustrated with AI-generated scenarios—not observed customer findings.')
    definitions = [
        ('Reaction A', 'Product Criticism', '#777777', 'SIM-0001',
         'Privacy concerns lead someone to reject the smart glasses. Traditional eyewear is not rejected.',
         'Product rejection can occur without wider-brand distrust.'),
        ('Reaction B', 'Brand Contagion', '#C62430', 'SIM-0080',
         'Distrust crosses from smart glasses to ordinary Ray-Ban eyewear. Product criticism alone is insufficient.',
         'Distrust could spread when the partnership changes perceptions of ordinary eyewear.'),
        ('Reaction C', 'Brand Insulation', '#171717', 'SIM-0133',
         'Someone attributes privacy responsibility to Meta while retaining trust in traditional Ray-Ban.',
         'Meta-focused blame can coexist with continued trust in traditional Ray-Ban.'),
    ]
    for column, (code, title, color, record_id, meaning, implication) in zip(st.columns(3), definitions):
        with column:
            row = by_id[record_id]
            extra = (f'<blockquote>{escape(row["text"])}</blockquote>'
                     f'<small>AI-generated illustration · {record_id}</small>'
                     f'<p><strong>Illustrative insight</strong><br>{escape(implication)}</p>')
            card(code, title, meaning, accent=color, extra=extra)


def render_question(records):
    import streamlit as st
    st.write('Smart eyewear creates opportunities for Ray-Ban. But could a privacy scandal involving '
             'Meta weaken customer trust in ordinary Ray-Ban eyewear—and expose shareholders to risk?')
    st.subheader('The Dilemma')
    for col, (title, text) in zip(st.columns(3), [
        ('Opportunity', 'Smart eyewear combines Ray-Ban design with new technology and services.'),
        ('Risk', 'Privacy scandals could weaken customer trust in the product and its partners.'),
        ('Shareholder Concern', 'If distrust reaches the wider Ray-Ban brand, its reputation and future earnings could be at risk.'),
    ]):
        with col: card('THE DILEMMA', title, text)
    st.markdown('### Our Qualified Answer')
    st.info(CONCLUSION)
    st.write('Shareholders are the primary stakeholder in this presentation. Customer reactions are '
             'the intermediate mechanism: lost trust could put brand reputation and future value at risk. '
             'This demonstration establishes neither brand damage, sales reductions nor shareholder losses.')
    st.markdown('**Privacy scandal → Possible customer distrust → Potential brand damage → Shareholder exposure**')
    st.subheader('Two components, different kinds of insight')
    for col, (title, text) in zip(st.columns(2), [
        ('Real Media Analysis', '32 genuine news, company and official sources document context. Existing coding explores privacy coverage, brand association and attributed roles. Unreviewed classifications remain provisional.'),
        ('Simulated Customer Reaction Analysis', '260 AI-generated scenarios illustrate product criticism, brand contagion and brand insulation. Constructed distributions and saved AI predictions are separate from empirical customer findings.'),
    ]):
        with col: card('ANALYTICAL COMPONENT', title, text)


def render_methodology():
    import streamlit as st
    st.subheader('Two stages: real reporting and simulated reactions')
    steps = [
        ('01 · REAL MEDIA ANALYSIS', '32 genuine sources',
         'News, company and official records → privacy coverage, brand association and attributed roles. Analytical labels remain provisional pending human review.'),
        ('02 · SIMULATED CUSTOMER REACTION ANALYSIS', '260 AI-generated scenarios',
         'Existing news context → constructed Reactions A/B/C → saved AI analysis: 220 accepted, 40 rejected. Illustrations, not independent customer evidence.'),
    ]
    # CSS grid becomes a vertical process diagram on narrow screens.
    items = []
    for index, (kind, title, description) in enumerate(steps):
        items.append(f'<div class="process-step"><small>{escape(kind)}</small><strong>{escape(title)}</strong>'
                     f'<p>{escape(description)}</p></div>')
        if index < len(steps)-1: items.append('<span class="process-arrow" aria-hidden="true">→</span>')
    st.markdown('<div class="story-process" role="group" aria-label="Research process">'+''.join(items)+'</div>', unsafe_allow_html=True)
    st.warning('Real sources provide context. Synthetic reactions illustrate possibilities. Model agreement is a diagnostic against unvalidated design labels, not independent evidence of customer attitudes.')


def render_synthesis():
    import streamlit as st
    from src.ui.media_insights import load_media_snapshot, media_totals
    st.subheader('What we can—and cannot—conclude')
    st.info(CONCLUSION)
    try:
        report = load_media_snapshot()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f'Media synthesis is unavailable until its snapshot passes provenance checks: {exc}')
        return
    totals = media_totals(report['records'])
    n = totals['denominator']
    st.caption('This synthesis uses the full frozen corpus, independent of the Analysis filters. Media coding is provisional; simulations are deliberately constructed.')
    points = [
        ('REAL MEDIA', 'What the sources establish',
         f"The {n} traceable sources document announcements, reporting, company responses and official scrutiny—not customer sentiment. "
         f"Provisional coding identifies privacy coverage in {totals['privacy_related_yes']}/{n} records and "
         f"direct traditional-brand references in {totals['wider_brand_association_explicit']}/{n}. The latter concern favourable comparison/style continuity, not demonstrated damage."),
        ('SIMULATIONS', 'What the reactions illustrate',
         'The 260 generated scenarios make three possible mechanisms visible: product criticism (Reaction A), wider-brand distrust (Reaction B), and brand insulation (Reaction C). Scenario frequencies were designed; model agreement is not independent validation.'),
        ('EVIDENCE BOUNDARY', 'What remains unknown',
         'We have not measured actual customer trust, spillover prevalence, sales reductions, pricing effects or shareholder losses. Media naming, official inquiries and simulated reactions cannot establish causal brand damage or financial exposure.'),
    ]
    for col, (kind, title, text) in zip(st.columns(3), points):
        with col: card(kind, title, text)
    st.write('For shareholders, customer trust is a possible link between a privacy controversy and brand value. '
             'The media analysis documents the context; the simulations illustrate how reactions might differ. '
             'Whether those reactions occur among real customers, and whether they affect shareholder value, remains an empirical question.')
    st.caption('Detailed model diagnostics, research limitations and the earlier strategic recommendations remain in Research Appendix.')


def render_recommendations():
    import streamlit as st
    st.subheader('Protect trust as eyewear and AI converge')
    st.info(CONCLUSION)
    st.write('Ray-Ban should make privacy responsibilities clear, show that safeguards work, and protect '
             'trust in its traditional eyewear. Customer trust can support brand reputation and future '
             'shareholder value; this demonstration does not measure a financial effect.')
    priorities = [
        ('01 · 2026–2027', 'Clarify accountability', 'Publish a joint, plain-language responsibility map covering capture, processing, vendor access and deletion. Train retailers to explain each partner’s role.', 'Look for: understandable disclosures and tested customer comprehension.'),
        ('02 · 2027–2028', 'Make privacy safeguards verifiable', 'Independently evaluate recording indicators, privacy choices and vendor-access controls. Explain findings and limitations publicly.', 'Look for: independent tests, access audits and documented incident responses.'),
        ('03 · THROUGH 2030', 'Protect traditional-brand equity', 'Monitor trust in ordinary Ray-Ban eyewear separately from smart-glasses adoption. Investigate when customers connect privacy concerns to the wider brand.', 'Look for: genuine customer studies separating product rejection from core-brand distrust.'),
    ]
    for col, (horizon, title, action, measure) in zip(st.columns(3), priorities):
        with col: card(horizon, title, action, accent='#C62430', extra=f'<p><small>{escape(measure)}</small></p>')
    st.caption('Recommendations are proposed strategic responses, not company commitments, measured outcomes or forecasts.')


def render_label_basis_guide():
    import streamlit as st
    st.write(LABEL_BASIS_GUIDE)
    st.space('small')


def render_count_chart(counts, title, interpretation, *, basis, field=None, show_basis=True):
    import streamlit as st
    values = [{'Label': readable(key), 'Scenarios': value} for key, value in counts.items()]
    st.markdown('**'+title+'**', help=interpretation)
    if show_basis:
        st.caption(f'{basis} · n={sum(counts.values())} simulated scenarios')
    if not values or not sum(counts.values()):
        st.info('No scenarios match these filters.')
        return
    colors = {'Explicit wider-brand distrust':'#C62430', 'Implicit brand association':'#BE777C',
              'No spillover':'#424242', 'Unclear / not stated':'#A6A6A6',
              'Negative':'#C62430', 'Positive':'#424242', 'Mixed':'#BE777C', 'Neutral':'#A6A6A6'}
    if field == 'purchase_intent':
        for row in values:
            row['Label'] = {'Positive':'More willing to purchase', 'Negative':'Less willing to purchase'}.get(row['Label'],row['Label'])
    st.vega_lite_chart({'data': {'values': values}, 'mark': {'type':'bar', 'cornerRadiusEnd':3},
        'height': max(130, len(values)*36),
        'encoding': {'y': {'field':'Label', 'type':'nominal', 'sort':None, 'title':None,
                           'axis':{'labelLimit':180, 'labelOverlap':False}},
                     'x': {'field':'Scenarios', 'type':'quantitative', 'title':'Simulated scenario count', 'axis':{'tickMinStep':1}},
                     'color': {'field':'Label', 'type':'nominal', 'legend':None,
                               'scale':{'domain':[r['Label'] for r in values],
                                        'range':[colors.get(r['Label'],'#424242') for r in values]}},
                     'tooltip':[{'field':'Label'}, {'field':'Scenarios','type':'quantitative'}]},
        'config': {'view':{'stroke':None}, 'axis':{'labelFontSize':12, 'titleFontSize':12,
                                                'labelColor':'#606060', 'titleColor':'#606060'}}},
        width='stretch', theme=None)
