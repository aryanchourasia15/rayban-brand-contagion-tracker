import copy
import json
import unittest

from src.analysis.schema import LABELS, TOPICS, validate_labels, needs_review
from tests.contagion_support import examples


class TestContagionSchema(unittest.TestCase):
    def test_synthetic_examples_cover_all_categories(self):
        cases = examples()
        for case in cases:
            with self.subTest(case=case['case']):
                self.assertEqual(validate_labels(json.dumps(case['labels']), case['text']), case['labels'])
        for field, values in LABELS.items():
            self.assertEqual({case['labels'][field] for case in cases}, set(values))
        self.assertEqual({topic for case in cases for topic in case['labels']['topic']}, set(TOPICS))

    def test_strict_types_enums_and_fields(self):
        case = examples()[0]
        for field, value in [('sentiment', 'happy'), ('target', []), ('confidence', True),
                             ('confidence', float('nan')), ('confidence', float('inf')),
                             ('confidence', -0.1), ('confidence', 1.1), ('topic', []),
                             ('topic', ['privacy', 'privacy']), ('topic', [False]),
                             ('rationale', ''), ('rationale', 'x' * 1001),
                             ('evidence_quotes', ['invented quotation']), ('evidence_quotes', [])]:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    validate_labels({**case['labels'], field: value}, case['text'])
        for labels in ({}, {**case['labels'], 'extra': True}, None):
            with self.assertRaises(ValueError):
                validate_labels(labels, case['text'])
        with self.assertRaises(ValueError):
            validate_labels('{"sentiment":"positive","sentiment":"negative"}', case['text'])

    def test_product_only_and_meta_only_cannot_be_explicit(self):
        for case in [examples()[0], examples()[2]]:
            with self.subTest(case=case['case']), self.assertRaisesRegex(ValueError, 'Product-only'):
                validate_labels({**case['labels'], 'spillover': 'explicit'}, case['text'])

    def test_model_cannot_relabel_product_criticism_as_core_brand_damage(self):
        case = examples()[0]
        for text in [case['text'],
                     "I won't buy Ray-Ban Meta because of privacy. I love Ray-Ban sunglasses.",
                     "I won't buy Ray-Ban Meta because of privacy but I love Ray-Ban sunglasses.",
                     "Ray-Ban sunglasses look great and I won't buy Ray-Ban Meta because of privacy."]:
            labels = {**case['labels'], 'target': 'both', 'spillover': 'explicit', 'evidence_quotes': [text]}
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_labels(labels, text)

    def test_negated_distrust_and_product_before_core_are_not_explicit(self):
        for text in ["I do not distrust Ray-Ban because of Meta privacy concerns.",
                     "I won't buy Ray-Ban Meta since Ray-Ban sunglasses suit me better."]:
            labels = {**examples()[0]['labels'], 'target': 'both', 'spillover': 'explicit', 'evidence_quotes': [text]}
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_labels(labels, text)

    def test_review_flags_and_confidence_boundaries(self):
        for case in examples():
            if case['labels']['spillover'] in ('explicit', 'implicit', 'unclear'):
                self.assertTrue(needs_review(case['labels']))
        labels = copy.deepcopy(examples()[0]['labels'])
        labels['confidence'] = 0.69
        self.assertTrue(needs_review(labels))
        labels['confidence'] = 0.7
        self.assertFalse(needs_review(labels))

    def test_evidence_is_exact_original_text_not_normalized(self):
        case = examples()[3]
        with self.assertRaises(ValueError):
            validate_labels({**case['labels'], 'evidence_quotes': [case['text'].lower()]}, case['text'])
