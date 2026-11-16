"""Human-label evaluation; no inference, model training or external dependencies."""
from src.analysis.schema import LABELS, TOPICS
from src.analysis.storage import research_predictions


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def binary_metrics(predicted, expected, positive='explicit'):
    if len(predicted) != len(expected):
        raise ValueError('Predictions and human labels must be paired.')
    tp = sum(p == positive and t == positive for p, t in zip(predicted, expected))
    fp = sum(p == positive and t != positive for p, t in zip(predicted, expected))
    fn = sum(p != positive and t == positive for p, t in zip(predicted, expected))
    tn = len(expected) - tp - fp - fn
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, support=tp + fn, n=len(expected),
                accuracy=_ratio(tp + tn, len(expected)), precision=_ratio(tp, tp + fp),
                recall=_ratio(tp, tp + fn), f1=_ratio(2 * tp, 2 * tp + fp + fn))


def evaluate_pairs(pairs):
    """Evaluate already paired, validated label dictionaries (including synthetic tests)."""
    for prediction, truth in pairs:
        for labels in (prediction, truth):
            if not isinstance(labels.get('topic'), list) or not labels['topic'] or any(t not in TOPICS for t in labels['topic']):
                raise ValueError('Unknown evaluation topic.')
    result = {'n': len(pairs), 'fields': {}}
    for field, choices in LABELS.items():
        predicted = [p[field] for p, _ in pairs]
        expected = [t[field] for _, t in pairs]
        if any(v not in choices for v in predicted + expected):
            raise ValueError('Unknown evaluation label.')
        confusion = {truth: {guess: 0 for guess in choices} for truth in choices}
        for guess, truth in zip(predicted, expected):
            confusion[truth][guess] += 1
        result['fields'][field] = dict(accuracy=_ratio(sum(p == t for p, t in zip(predicted, expected)), len(pairs)),
            per_class={choice: binary_metrics(predicted, expected, choice) for choice in choices}, confusion=confusion)
    topic_results = {}
    for topic in TOPICS:
        predicted = [topic in p['topic'] for p, _ in pairs]
        expected = [topic in t['topic'] for _, t in pairs]
        topic_results[topic] = binary_metrics(predicted, expected, True)
    result['topics'] = topic_results
    result['explicit_spillover'] = result['fields']['spillover']['per_class']['explicit']
    return result


def evaluate_research(db_path=None):
    selected = research_predictions(db_path)
    reviewed = [row for row in selected if row['human_labels'] is not None]
    result = evaluate_pairs([(row['prediction'], row['human_labels']) for row in reviewed])
    result.update(eligible_predictions=len(selected), reviewed_predictions=len(reviewed),
                  unreviewed_predictions=len(selected) - len(reviewed),
                  selection='Latest successful AI run per authorized real record, latest review for that run',
                  versions=sorted({(row['model_name'], row['model_version'], row['prompt_version']) for row in reviewed}))
    return result
