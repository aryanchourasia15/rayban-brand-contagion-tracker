"""Presentation of frozen evidence and scenarios; no inference or data mutation."""
from html import escape

QUESTION = "Can Meta's Privacy Controversies Damage the Ray-Ban Brand?"
CONCLUSION = ('Brand contagion is a plausible strategic risk, '
              'but actual wider-brand damage has not been established.')
SECTIONS = ['Strategic Question', 'Evidence & Methodology', 'Brand Contagion Analysis',
            'Strategic Recommendations', 'Research Appendix']
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
    st.caption('Hypotheses illustrated with existing AI-generated scenarios — not observed customer findings.')
    definitions = [
        ('H1', 'Product Criticism', '#777777', 'SIM-0001',
         'Privacy concerns lead someone to reject the smart glasses. Traditional eyewear is not rejected.',
         'Address product safeguards and explain how recording and data use work.'),
        ('H2', 'Brand Contagion', '#C62430', 'SIM-0080',
         'Distrust crosses from smart glasses to ordinary Ray-Ban eyewear. Product criticism alone is insufficient.',
         'Treat brand endorsement as a trust obligation extending beyond the device.'),
        ('H3', 'Brand Insulation', '#171717', 'SIM-0133',
         'Someone attributes privacy responsibility to Meta while retaining trust in traditional Ray-Ban.',
         'Clarify accountability while keeping Ray-Ban accountable for its own commitments.'),
    ]
    for column, (code, title, color, record_id, meaning, implication) in zip(st.columns(3), definitions):
        with column:
            row = by_id[record_id]
            extra = (f'<blockquote>{escape(row["text"])}</blockquote>'
                     f'<small>AI-generated illustration · {record_id}</small>'
                     f'<p><strong>Strategic implication</strong><br>{escape(implication)}</p>')
            card(code, title, meaning, accent=color, extra=extra)


def render_question(records):
    import streamlit as st
    st.write('Smart eyewear brings fashion, consumer technology and AI into the same product. '
             'For Ray-Ban, the opportunity is useful innovation; the dilemma is whether privacy concerns '
             'remain with the device and Meta, or reach the trust attached to ordinary eyewear.')
    for col, (title, text) in zip(st.columns(3), [
        ('The opportunity', 'Familiar design and optical distribution can help bring smart eyewear into everyday use.'),
        ('The legitimacy challenge', 'Recording, bystander expectations and data handling raise questions beyond technical performance.'),
        ('The brand boundary', 'Ray-Ban endorsement may link these concerns to traditional eyewear, but that transfer must not be assumed.'),
    ]):
        with col: card('STRATEGIC DILEMMA', title, text)
    st.markdown('### Our qualified answer')
    st.info(CONCLUSION)
    st.caption('This demonstration explores conditions under which distrust could spread. It does not measure its prevalence or establish causation.')
    render_mechanisms(records)


def render_methodology():
    import streamlit as st
    st.subheader('From real context to illustrative strategic mechanisms')
    steps = [
        ('01 · REAL EVIDENCE', '32 genuine news sources', 'Sourced developments and company / official responses; media is not customer opinion.'),
        ('02 · SYNTHETIC', '260 AI-generated scenarios', 'Constructed reactions grounded in the news, with deliberately assigned scenario categories.'),
        ('03 · RECORDED AI', 'Local AI classification', 'Saved Qwen2.5:3b outputs: 220 accepted and 40 rejected. No live inference.'),
        ('04 · INTERPRETATION', 'Brand contagion analysis', 'Compare product criticism, wider-brand distrust and brand insulation; keep label bases separate.'),
        ('05 · STRATEGY', 'Implications through 2030', 'Proposed actions and evidence to seek, rather than forecasts or established brand damage.'),
    ]
    # CSS grid becomes a vertical process diagram on narrow screens.
    items = []
    for index, (kind, title, description) in enumerate(steps):
        items.append(f'<div class="process-step"><small>{escape(kind)}</small><strong>{escape(title)}</strong>'
                     f'<p>{escape(description)}</p></div>')
        if index < len(steps)-1: items.append('<span class="process-arrow" aria-hidden="true">→</span>')
    st.markdown('<div class="story-process" role="group" aria-label="Research process">'+''.join(items)+'</div>', unsafe_allow_html=True)
    st.warning('Real sources provide context. Synthetic reactions illustrate possibilities. Model agreement is a diagnostic against unvalidated design labels, not independent evidence of customer attitudes.')


def render_recommendations():
    import streamlit as st
    st.subheader('Protect trust as eyewear and AI converge')
    st.info(CONCLUSION)
    st.write('Responsibility attribution can contain or transmit distrust. Ray-Ban’s endorsement can make '
             'privacy expectations relevant to the wider brand, even when Meta operates the technology. '
             'Market convergence therefore requires both customer usefulness and social legitimacy: '
             'trust in what the product does, how it treats people, and who answers when expectations fail.')
    priorities = [
        ('01 · 2026–2027', 'Clarify accountability', 'Publish a joint, plain-language responsibility map covering capture, processing, vendor access and deletion. Train retailers to explain each partner’s role.', 'Look for: understandable disclosures and tested customer comprehension.'),
        ('02 · 2027–2028', 'Make privacy safeguards verifiable', 'Independently evaluate recording indicators, privacy choices and vendor-access controls. Explain findings and limitations publicly.', 'Look for: independent tests, access audits and documented incident responses.'),
        ('03 · THROUGH 2030', 'Protect traditional-brand equity', 'Monitor trust in ordinary Ray-Ban eyewear separately from smart-glasses adoption. Investigate when customers connect privacy concerns to the wider brand.', 'Look for: genuine customer studies separating product rejection from core-brand distrust.'),
    ]
    for col, (horizon, title, action, measure) in zip(st.columns(3), priorities):
        with col: card(horizon, title, action, accent='#C62430', extra=f'<p><small>{escape(measure)}</small></p>')
    st.caption('Recommendations are proposed strategic responses, not company commitments, measured outcomes or forecasts.')


def render_count_chart(counts, title, interpretation, *, basis, field=None):
    import streamlit as st
    values = [{'Label': readable(key), 'Scenarios': value} for key, value in counts.items()]
    st.markdown('**'+title+'**')
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
    st.write(interpretation)
