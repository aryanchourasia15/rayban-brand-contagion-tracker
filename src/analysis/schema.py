"""JSON contract and conservative evidence checks, without new dependencies."""
import json
import math
import re

LABELS = {
    'sentiment': ('positive', 'negative', 'neutral', 'mixed'),
    'target': ('Ray-Ban Meta', 'core Ray-Ban', 'Meta', 'both', 'unclear'),
    'responsibility': ('Ray-Ban', 'Meta', 'both', 'unclear'),
    'spillover': ('explicit', 'implicit', 'none', 'unclear'),
    'purchase_intent': ('positive', 'negative', 'unclear'),
}
TOPICS = ('privacy', 'recording', 'fashion', 'technology', 'convenience', 'safety', 'other')
JSON_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        **{key: {'type': 'string', 'enum': list(values)} for key, values in LABELS.items()},
        'topic': {'type': 'array', 'items': {'type': 'string', 'enum': list(TOPICS)}, 'minItems': 1, 'uniqueItems': True},
        'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
        'rationale': {'type': 'string', 'minLength': 1, 'maxLength': 1000},
        'evidence_quotes': {'type': 'array', 'items': {'type': 'string', 'minLength': 1}, 'minItems': 1, 'maxItems': 5},
    },
}
JSON_SCHEMA['required'] = list(JSON_SCHEMA['properties'])


def _no_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON property.')
        value[key] = item
    return value


def validate_labels(value, text, *, evidence_version='legacy-1.0'):
    """Validate complete labels and exact evidence. Return a detached JSON value.

    Explicit-spillover checks deliberately favor review over false brand-damage claims.
    These checks are safeguards, not a substitute for semantic human validation.
    """
    if evidence_version not in ('legacy-1.0', 'context-evidence-2.0'):
        raise ValueError('Unknown evidence validation version.')
    if isinstance(value, str):
        value = json.loads(value, object_pairs_hook=_no_duplicate_keys)
    if not isinstance(value, dict) or set(value) != set(JSON_SCHEMA['required']):
        raise ValueError('Classification must contain exactly the required fields.')
    for key, choices in LABELS.items():
        if not isinstance(value[key], str) or value[key] not in choices:
            raise ValueError(f'Invalid {key} label.')
    topics = value['topic']
    if not isinstance(topics, list) or not topics or any(not isinstance(x, str) or x not in TOPICS for x in topics) or len(set(topics)) != len(topics):
        raise ValueError('Invalid or duplicate topics.')
    confidence = value['confidence']
    if type(confidence) not in (float, int) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError('Confidence must be a finite number from 0 to 1.')
    if not isinstance(value['rationale'], str) or not value['rationale'].strip() or len(value['rationale']) > 1000:
        raise ValueError('A concise rationale is required.')
    quotes = value['evidence_quotes']
    if not isinstance(quotes, list) or not 1 <= len(quotes) <= 5 or any(not isinstance(q, str) or not q.strip() or q not in text for q in quotes):
        raise ValueError('Evidence quotations must be exact nonempty substrings of the original text.')
    if value['spillover'] == 'explicit':
        if value['target'] not in ('core Ray-Ban', 'both') or value['sentiment'] not in ('negative', 'mixed'):
            raise ValueError('Product-only/Meta-only criticism cannot establish explicit brand spillover.')
        supported = False
        for quote in quotes:
            quote = quote.lower().replace('’', "'")
            # Do not combine product criticism in one clause with brand praise in another.
            for clause in re.split(r'[.!?;\n]|\b(?:but|however|although|yet|and)\b', quote):
                without_product = re.sub(r'ray[ -]?ban\s+(?:meta|stories)', '<product>', clause)
                criticism = re.search(r"distrust|don't trust|do not trust|lost (?:my )?trust|won't buy|will not buy|never buy|avoid|boycott|stop buying", without_product)
                following = without_product[criticism.end():] if criticism else ''
                core = re.search(r'ray[ -]?ban|(?:whole|entire|wider) brand|traditional (?:frames|sunglasses)', following)
                product_first = core and '<product>' in following[:core.start()]
                negated = re.search(r"(?:don't|do not|not|never)\s+(?:distrust|avoid|boycott|stop buying)", without_product)
                controversy = re.search(r'privacy|recording|surveillance|meta|smart glasses|camera', clause)
                connection = re.search(r'because|due to|after|since|made me|makes me|so ', clause)
                supported |= bool(core and criticism and controversy and connection and not product_first and not negated)
        if not supported and evidence_version == 'context-evidence-2.0':
            from src.analysis.spillover_evidence import explicit_core_support
            supported = explicit_core_support(quotes)
        if not supported:
            raise ValueError('Explicit spillover requires quoted core-brand distrust linked to the controversy; otherwise use unclear/implicit.')
    return json.loads(json.dumps(value, allow_nan=False))


def needs_review(labels):
    return labels['confidence'] < 0.7 or labels['spillover'] in ('explicit', 'implicit', 'unclear') or labels['target'] == 'unclear'
