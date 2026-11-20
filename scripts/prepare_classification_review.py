"""Build 50 AI-assisted editorial proposals from saved text; no inference or imports.

Original scenario labels/predictions remain untouched. These authored proposals
are not an independent rater, human validation or replacement benchmark truth.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis.schema import LABELS, TOPICS, validate_labels
from src.analysis.simulation import fingerprint

# sentiment, focal target, explicit responsibility, spillover, purchase intention,
# topics, text-grounded rationale. 'Target' concerns the evaluated/criticised
# entity; praising core frames does not make them a target of criticism.
PROPOSALS = {
1: ('negative','product','unclear','none','negative','privacy recording technology','Refusal to buy these camera glasses is product-only; no wider-brand rejection or company-specific blame is stated.'),
7: ('negative','product','both','none','unclear','privacy recording','Both companies are explicitly held accountable for features. Shared responsibility is not wider-brand distrust; no buying decision is stated.'),
13: ('negative','product','unclear','none','unclear','privacy recording','Camera intrusion is criticised sarcastically; ordinary eyewear and explicit company blame are absent.'),
19: ('mixed','product','unclear','none','negative','privacy recording','The speaker welcomes a possible safeguard but refuses Ray-Ban Meta. The ordinary-sunglasses phrase does not state distrust of traditional frames.'),
25: ('mixed','product','unclear','none','unclear','privacy recording technology','Cool features and an intrusive camera form a mixed product assessment. No core-brand distrust or purchase commitment is expressed.'),
31: ('mixed','product','unclear','none','negative','privacy recording fashion','Reliable old frames are defended while Meta-branded smart products are avoided. A product name alone does not establish explicit corporate responsibility.'),
37: ('negative','product','unclear','none','negative','privacy recording','The compound product name is not a separate assignment of blame to Ray-Ban. The conditional refusal concerns these glasses only.'),
43: ('mixed','product','unclear','none','unclear','privacy safety fashion','Traditional sunglasses are preferred, so the recording concern does not establish wider-brand damage. The tracking claim is a simulated belief, not a verified capability.'),
49: ('negative','product','unclear','none','unclear','privacy','The simulated policy accusation names no responsible company and expresses no purchase intention or wider-brand consequence. It is not a factual finding about policy.'),
55: ('negative','product','unclear','none','unclear','privacy recording','The conditional move to ordinary sunglasses rejects the smart product; it does not reject traditional Ray-Ban or explicitly assign company blame.'),
61: ('negative','both','unclear','explicit','unclear','privacy','Data-gathering doubt is expressly extended beyond the glasses to the whole brand now. The original negative buying label is unsupported.'),
62: ('negative','core','unclear','explicit','unclear','privacy technology','The text directly links smart-glasses AI to doubt about trusting regular Ray-Ban sunglasses. This is qualified distrust, not a resolved buying decision.'),
63: ('negative','core','unclear','explicit','unclear','privacy','Trust in traditional Ray-Ban and wearing old frames are questioned after privacy concerns. The link is explicit even though the attitude remains tentative.'),
64: ('mixed','product','unclear','none','unclear','privacy fashion','Sticking with regular frames while skipping smart glasses preserves a boundary. The designed explicit-spillover label is contradicted by the text.'),
65: ('negative','core','unclear','explicit','unclear','technology fashion','Association with smart glasses is expressly said to cause doubt about all products. This is broader technology-linked distrust; privacy is not actually named.'),
66: ('mixed','meta','unclear','none','negative','other fashion','Distrust of Meta coexists with a safer traditional-Ray-Ban alternative. Refusing Meta products does not reject the wider Ray-Ban brand; privacy is unstated.'),
67: ('negative','core','unclear','implicit','unclear','technology','Smart-glasses issues add to an existing wider-brand scepticism. Privacy-specific causation and a buying decision are not established.'),
68: ('mixed','core','unclear','explicit','unclear','privacy technology','Privacy concerns explicitly prevent willingness to wear regular Ray-Ban frames. Excitement about the technology remains; wearing is not necessarily purchasing.'),
69: ('mixed','core','unclear','unclear','unclear','technology','Hesitant to give up trust can mean reluctance to abandon the brand, not loss of trust. Do not force a negative-spillover conclusion.'),
70: ('mixed','unclear','unclear','unclear','unclear','privacy recording','Traditional-brand trust is expressly retained. Their glasses and hypothetical tracking do not resolve whether rejection concerns smart glasses or ordinary frames.'),
71: ('negative','both','Meta','implicit','unclear','privacy technology','Meta is explicitly distrusted over privacy. Traditional-brand doubt is emerging, but avoid everything has ambiguous scope and the quoted evidence lacks a decisive causal core-brand rejection.'),
72: ('mixed','product','unclear','none','unclear','privacy','Still trusting traditional Ray-Ban is explicit; partnership unease does not by itself revoke that trust.'),
73: ('mixed','product','unclear','none','unclear','privacy','Traditional Ray-Ban is expressly trusted despite partnership concerns. No wider rejection or purchase refusal is stated.'),
74: ('negative','core','unclear','implicit','unclear','privacy technology','Past trust contrasts with current uncertainty about integration practices. The broader effect is suggested, without a clear present rejection or company-specific blame.'),
75: ('mixed','product','unclear','implicit','unclear','privacy technology','The partnership is worrying while traditional glasses are still worn and trusted. Possible association is suggested; current wider distrust remains ambiguous.'),
76: ('mixed','both','unclear','implicit','unclear','privacy technology','Might spill over is a prospective concern, not a report that trust has already transferred. Core trust is still stated.'),
77: ('mixed','product','unclear','none','unclear','privacy fashion','Preference for classic frames protects the traditional brand while criticising smart-glasses privacy.'),
78: ('mixed','both','unclear','explicit','unclear','privacy','Privacy concerns are directly connected to questioning whether to wear Ray-Ban at all, alongside praise for traditional glasses. The saved quote with an added period was not exact.'),
79: ('mixed','both','unclear','explicit','unclear','privacy','Partnership privacy unease is expressly said to cause doubt about trusting the brand across all products. No company-specific blame or resolved purchase decision is stated.'),
80: ('negative','core','unclear','explicit','unclear','privacy technology','Privacy issues are explicitly said to spill over into not wanting regular eyewear. This is direct core scope and causation, even without boycott vocabulary.'),
81: ('negative','both','both','implicit','unclear','privacy','Both firms are distrusted on this one, which may restrict criticism to the smart-glasses product. Past traditional-brand affection alone does not prove current wider rejection.'),
82: ('mixed','product','unclear','none','unclear','privacy recording','Privacy fear concerns these smart glasses; the past liking for traditional frames is not explicitly withdrawn.'),
83: ('mixed','both','unclear','explicit','unclear','privacy','The speaker still likes daily-wear frames but expressly extends smart-glasses privacy doubt to the whole brand now.'),
84: ('negative','core','unclear','implicit','unclear','technology fashion','An alternative-frame preference follows smart-technology aversion. Privacy is not stated, so do not assert explicit privacy-contagion causation.'),
85: ('mixed','both','unclear','implicit','unclear','privacy fashion','Classic design remains appreciated; brand-integrity concern suggests association without an explicit loss of trust or refusal.'),
86: ('negative','both','Ray-Ban','implicit','unclear','privacy technology fashion','The speaker criticises abandoning the core brand for gadgets. The described strategic choice points to Ray-Ban, but a current rejection of ordinary products is not stated.'),
87: ('negative','core','unclear','explicit','unclear','privacy technology','The conditional privacy concern is directly linked to not wanting association with the traditional brand. This is stated potential rejection, not observed purchasing behaviour.'),
88: ('mixed','core','unclear','explicit','unclear','privacy','Privacy concerns explicitly make the speaker wary of the whole brand; subsequent avoidance is conditional. Appreciation for the frames remains.'),
89: ('negative','core','unclear','implicit','unclear','privacy','Concern reaches traditional glasses too, but their recent move does not specify a clear causal mechanism or actual loss of trust.'),
90: ('mixed','core','unclear','explicit','unclear','privacy fashion','Smart-glasses privacy concern is expressly said to question considering other products. It is qualified purchase consideration, not a settled refusal.'),
91: ('mixed','product','unclear','unclear','unclear','privacy technology','Past frame appreciation and current AI data concern do not establish whether traditional-brand trust changes.'),
97: ('negative','both','unclear','implicit','unclear','technology fashion','A hypothetical spread to traditional frames is feared rather than reported as an actual trust change. Privacy itself is not stated.'),
103: ('mixed','both','unclear','implicit','unclear','privacy technology','The speaker anticipates others viewing traditional frames as less trustworthy, not a definite personal rejection. Technical appeal also remains.'),
109: ('mixed','both','unclear','unclear','unclear','privacy safety technology','The traditional-brand safety question is unresolved. A question is not evidence of a definite negative brand judgement.'),
115: ('mixed','product','unclear','none','unclear','privacy recording technology','Traditional Ray-Bans are explicitly described as unaffected, which contradicts the designed implicit-spillover label.'),
121: ('mixed','meta','Meta','none','unclear','privacy technology','Meta is asked to improve data security while traditional Ray-Ban is explicitly trusted. Trust does not prove purchase intention.'),
133: ('positive','core','Meta','none','unclear','privacy fashion','Meta is assigned a processing role without an adverse claim; the express evaluation of traditional frames is trust. No buying intention is stated.'),
145: ('mixed','meta','Meta','none','unclear','privacy','Meta is explicitly blamed while traditional Ray-Ban is trusted. This is insulation, not negative wider-brand spillover.'),
157: ('mixed','meta','Meta','none','unclear','privacy technology','Meta must prove privacy effectiveness, while core trust and technical appeal remain. No wider rejection or purchase commitment is stated.'),
169: ('mixed','meta','Meta','none','unclear','privacy fashion','Meta blame and traditional-brand trust coexist. Win-win expresses satisfaction, not an explicit intention to buy.'),
}
TARGETS = dict(product='Ray-Ban Meta', core='core Ray-Ban', meta='Meta', both='both', unclear='unclear')


def build():
    dataset_path = ROOT / 'demo/grounded_scenarios.json'
    output_path = ROOT / 'demo/simulation_classifications.json'
    dataset = json.loads(dataset_path.read_text(encoding='utf-8'))
    output = json.loads(output_path.read_text(encoding='utf-8'))
    predictions = {row['case']: row for row in output['results']}
    records = []
    for row in dataset['records']:
        number = int(row['synthetic_id'].split('-')[1])
        if number not in PROPOSALS:
            continue
        sentiment, target, responsibility, spillover, purchase, topics, reason = PROPOSALS[number]
        labels = dict(sentiment=sentiment, target=TARGETS[target], responsibility=responsibility,
                      spillover=spillover, purchase_intent=purchase, topic=topics.split())
        if any(labels[key] not in choices for key, choices in LABELS.items()) or any(t not in TOPICS for t in labels['topic']):
            raise ValueError('Invalid authored proposal label.')
        prediction = predictions[row['synthetic_id']]
        stratum = ('all_designed_explicit' if 61 <= number <= 90 else
                   'product_or_Meta_criticism' if number < 61 else 'implicit_or_brand_protection')
        replay = {}
        for version in ('legacy-1.0', 'context-evidence-2.0'):
            try:
                validate_labels(prediction['raw_output'], row['text'], evidence_version=version)
                replay[version] = 'passes'
            except (ValueError, TypeError, KeyError) as exc:
                replay[version] = str(exc)
        records.append(dict(synthetic_id=row['synthetic_id'], is_synthetic=True, stratum=stratum,
            text=row['text'], simulated_publication_year=row['simulated_publication_year'],
            related_article_ids=row['related_article_ids'], original_design_labels=row['expected_labels'],
            historical_prediction=prediction['parsed_output'], historical_status=prediction['status'],
            historical_validation=prediction.get('validation'), proposed_labels=labels,
            evidence_quotes=[row['text']], proposal_rationale=reason,
            uncertainty_flag=spillover in ('implicit','unclear') or number in (62,63,65,68,70,71,78,79,81,87,88,90),
            review_status='AI-assisted proposal — pending independent human validation',
            safeguard_replay=replay))
    if len(records) != 50 or Counter(r['stratum'] for r in records) != {
            'all_designed_explicit':30,'product_or_Meta_criticism':10,'implicit_or_brand_protection':10}:
        raise ValueError('Expected the predefined stratified 50-record review.')
    report = dict(kind='ai_assisted_review_proposals_not_human_validation', is_synthetic=True,
        review_date='2026-11-20', method='AI-assisted editorial assessment of existing text; no new generation or model inference.',
        policy='Qualified doubt can be explicit when a direct product-to-core causal link is stated; concerns, hypothetical spread and core-brand defence alone are not explicit. Buying intent is not inferred from trust or wearing preference. Responsibility requires textual attribution.',
        source_hash_basis='Canonical JSON records; portable across Git line-ending conversion.',
        dataset_sha256=fingerprint(dataset['records']),
        predictions_sha256=fingerprint(output['results']),
        records=records, records_sha256=fingerprint(records),
        summary=dict(n=50, strata=dict(Counter(r['stratum'] for r in records)),
            proposed_spillover=dict(Counter(r['proposed_labels']['spillover'] for r in records)),
            designed_explicit_proposals=dict(Counter(r['proposed_labels']['spillover'] for r in records if r['stratum']=='all_designed_explicit'))))
    return report


if __name__ == '__main__':
    report = build()
    path = ROOT / 'demo/classification_review_proposals.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    buffer = io.StringIO(newline='')
    fields = ['synthetic_id','stratum','text','review_status','historical_status','original_design_labels',
              'historical_prediction','proposed_labels','evidence_quotes','proposal_rationale','uncertainty_flag']
    writer=csv.DictWriter(buffer,fieldnames=fields); writer.writeheader()
    for record in report['records']:
        writer.writerow({key:json.dumps(record[key],ensure_ascii=False) if isinstance(record[key],(dict,list)) else record[key] for key in fields})
    (ROOT / 'demo/classification_review_proposals.csv').write_bytes(buffer.getvalue().encode('utf-8-sig'))
    print(json.dumps(report['summary']))
