import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.analysis.engine import classify_record, classify_batch
from src.analysis.ollama_client import LocalModelError
from src.analysis.storage import (init_analysis_db, record_permission, get_history,
                                 append_review, research_predictions)
from src.analysis.evaluation import binary_metrics, evaluate_pairs, evaluate_research
from src.data.db import get_connection, insert_record, get_record_by_id
from tests.contagion_support import examples, classify_synthetic_fixture


class TestContagionEngine(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'analysis.db'
        init_analysis_db(self.db)
        self.case = examples()[0]
        self.client = MagicMock()
        self.client.inspect.return_value = dict(model_name='fixture:latest', model_version='digest-one', runtime_version='test-runtime')
        self.client.generate.return_value = json.dumps(self.case['labels'])
        patcher = patch('src.analysis.engine.OllamaClient', return_value=self.client)
        self.factory = patcher.start()
        self.addCleanup(patcher.stop)

    def add_record(self, case=None, synthetic=True, **overrides):
        return insert_record(dict(source='Imported', source_type='customer_discussion',
            collection_method='CSV import', text=(case or self.case)['text'],
            is_synthetic=synthetic) | overrides, db_path=self.db)

    def permit(self, record_id, **kwargs):
        return record_permission(record_id, 'synthetic-test-authorization', 'test-verifier',
                                 verified=True, db_path=self.db, **kwargs)

    def classify(self, record_id):
        return classify_record(record_id, 'fixture:latest', db_path=self.db)

    def test_all_synthetic_cases_use_mocked_ai_and_preserve_originals(self):
        for case in examples():
            with self.subTest(case=case['case']):
                record_id = self.add_record(case)
                self.client.generate.return_value = json.dumps(case['labels'])
                result = self.classify(record_id)
                self.assertEqual(result['labels'], case['labels'])
                self.assertEqual(get_record_by_id(record_id, self.db)['text'], case['text'])
                history = get_history(record_id, self.db)
                self.assertEqual(history['attempts'][0]['method'], 'ollama')
                self.assertEqual(history['attempts'][0]['model_version'], 'digest-one')
        self.assertEqual(research_predictions(self.db), [])

    def test_real_records_require_verified_permissions_and_revocations_block(self):
        record_id = self.add_record(synthetic=False)
        with self.assertRaises(PermissionError):
            self.classify(record_id)
        self.factory.assert_not_called()
        record_permission(record_id, 'test-unverified', 'test-verifier', verified=False, db_path=self.db)
        with self.assertRaises(PermissionError):
            self.classify(record_id)
        self.permit(record_id)
        self.assertEqual(self.classify(record_id)['status'], 'success')
        self.assertEqual(len(research_predictions(self.db)), 1)
        self.permit(record_id, revoke=True)
        with self.assertRaises(PermissionError):
            self.classify(record_id)
        self.assertEqual(research_predictions(self.db), [])
        self.assertEqual(len(get_history(record_id, self.db)['attempts']), 1)

    def test_permission_reference_and_verification_are_explicit(self):
        record_id = self.add_record(synthetic=False)
        for reference, reviewer, verified in [('', 'test', True), ('test', '', True), ('test', 'test', 1)]:
            with self.subTest(reference=reference, reviewer=reviewer, verified=verified), self.assertRaises(ValueError):
                record_permission(record_id, reference, reviewer, verified=verified, db_path=self.db)

    def test_media_invalid_and_missing_records_do_not_reach_model(self):
        for record_id in [self.add_record(source_type='media'), self.add_record(status='invalid'), 'missing']:
            with self.subTest(record_id=record_id), self.assertRaises(ValueError):
                self.classify(record_id)
        self.factory.assert_not_called()

    def test_invalid_model_json_labels_and_evidence_preserve_failed_raw_outputs(self):
        record_id = self.add_record()
        outputs = ['not JSON', json.dumps({**self.case['labels'], 'confidence': 2}),
                   json.dumps({**self.case['labels'], 'evidence_quotes': ['not in text']}),
                   json.dumps({**self.case['labels'], 'target': 'both', 'spillover': 'explicit'})]
        for raw in outputs:
            self.client.generate.return_value = raw
            self.assertEqual(self.classify(record_id)['status'], 'failed')
        history = get_history(record_id, self.db)['attempts']
        self.assertEqual([row['raw_output'] for row in history], outputs)
        self.assertTrue(all(row['labels_json'] is None and row['needs_review'] for row in history))

    def test_local_model_failure_is_audited_without_rule_fallback(self):
        record_id = self.add_record()
        self.client.inspect.side_effect = LocalModelError('unavailable')
        self.assertEqual(self.classify(record_id)['status'], 'failed')
        self.client.generate.assert_not_called()
        attempt = get_history(record_id, self.db)['attempts'][0]
        self.assertEqual(attempt['method'], 'ollama')
        self.assertEqual(attempt['model_version'], 'unavailable')
        self.client.close.assert_called_once()

    def test_generation_failure_is_audited(self):
        record_id = self.add_record()
        self.client.generate.side_effect = LocalModelError('network failure')
        self.assertEqual(self.classify(record_id)['status'], 'failed')
        self.assertEqual(len(get_history(record_id, self.db)['attempts']), 1)

    def test_permission_revoked_during_inference_prevents_commit(self):
        record_id = self.add_record(synthetic=False)
        self.permit(record_id)
        def revoke(*args):
            self.permit(record_id, revoke=True)
            return json.dumps(self.case['labels'])
        self.client.generate.side_effect = revoke
        with self.assertRaises(PermissionError):
            self.classify(record_id)
        self.assertEqual(get_history(record_id, self.db)['attempts'], [])

    def test_regrant_requires_new_prediction_for_research_metrics(self):
        record_id = self.add_record(synthetic=False)
        self.permit(record_id)
        first = self.classify(record_id)
        self.permit(record_id, revoke=True)
        self.permit(record_id)
        self.assertEqual(research_predictions(self.db), [])
        with self.assertRaises(PermissionError):
            append_review(first['attempt_id'], self.case['labels'], 'test', 'test', self.db)
        self.classify(record_id)
        self.assertEqual(len(research_predictions(self.db)), 1)

    def test_source_changes_during_inference_prevent_commit(self):
        record_id = self.add_record()
        def mutate(*args):
            conn = get_connection(self.db)
            try:
                with conn:
                    conn.execute('UPDATE records SET text=? WHERE record_id=?', ('changed synthetic text', record_id))
            finally:
                conn.close()
            return json.dumps(self.case['labels'])
        self.client.generate.side_effect = mutate
        with self.assertRaises(ValueError):
            self.classify(record_id)
        self.assertEqual(get_history(record_id, self.db)['attempts'], [])

    def test_permission_revoked_during_inspection_prevents_text_transmission(self):
        record_id = self.add_record(synthetic=False)
        self.permit(record_id)
        def inspect():
            self.permit(record_id, revoke=True)
            return dict(model_name='fixture', model_version='test', runtime_version='test')
        self.client.inspect.side_effect = inspect
        with self.assertRaises(PermissionError):
            self.classify(record_id)
        self.client.generate.assert_not_called()

    def test_reclassification_human_corrections_and_latest_selection(self):
        record_id = self.add_record(synthetic=False)
        self.permit(record_id)
        first = self.classify(record_id)
        corrected = {**self.case['labels'], 'spillover': 'unclear', 'confidence': 0.4}
        review_one = append_review(first['attempt_id'], corrected, 'reviewer-1', 'Ambiguous context', self.db)
        review_two = append_review(first['attempt_id'], self.case['labels'], 'reviewer-2', 'Product-only scope', self.db)
        self.assertGreater(review_two, review_one)
        selected = research_predictions(self.db)
        self.assertEqual(selected[0]['human_labels'], self.case['labels'])
        self.assertEqual(len(get_history(record_id, self.db)['reviews']), 2)
        self.assertEqual(evaluate_research(self.db)['n'], 1)
        self.client.inspect.return_value['model_version'] = 'digest-two'
        second = self.classify(record_id)
        self.assertGreater(second['attempt_id'], first['attempt_id'])
        self.assertEqual(len(research_predictions(self.db)), 1)
        self.assertIsNone(research_predictions(self.db)[0]['human_labels'])
        self.assertEqual(evaluate_research(self.db)['n'], 0)
        self.client.generate.return_value = 'broken'
        self.classify(record_id)
        self.assertEqual(research_predictions(self.db)[0]['attempt_id'], second['attempt_id'])

    def test_human_labels_are_validated_and_revocation_blocks_review(self):
        record_id = self.add_record(synthetic=False)
        self.permit(record_id)
        result = self.classify(record_id)
        with self.assertRaises(ValueError):
            append_review(result['attempt_id'], {**self.case['labels'], 'confidence': -1}, 'test', 'test', self.db)
        self.permit(record_id, revoke=True)
        with self.assertRaises(PermissionError):
            append_review(result['attempt_id'], self.case['labels'], 'test', 'test', self.db)

    def test_append_only_triggers_and_idempotent_initialization(self):
        record_id = self.add_record()
        self.permit(record_id)
        result = self.classify(record_id)
        append_review(result['attempt_id'], self.case['labels'], 'test', 'confirmed', self.db)
        init_analysis_db(self.db)
        conn = get_connection(self.db)
        try:
            for table in ('classification_permissions', 'classification_attempts', 'human_reviews'):
                for statement in (f'DELETE FROM {table}', f'UPDATE {table} SET created_at=created_at'):
                    with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                        with conn:
                            conn.execute(statement)
        finally:
            conn.close()
        self.assertEqual(len(get_history(record_id, self.db)['attempts']), 1)

    def test_synthetic_rule_labels_are_separate_and_excluded(self):
        record_id = self.add_record()
        classify_synthetic_fixture(record_id, self.db)
        self.assertEqual(get_history(record_id, self.db)['attempts'][0]['method'], 'rule_based_test')
        self.assertEqual(evaluate_research(self.db)['eligible_predictions'], 0)
        real = self.add_record(synthetic=False)
        self.permit(real)
        with self.assertRaises(ValueError):
            classify_synthetic_fixture(real, self.db)

    def test_real_metrics_include_only_latest_reviewed_real_predictions(self):
        explicit = examples()[1]
        record_id = self.add_record(explicit, synthetic=False)
        self.permit(record_id)
        self.client.generate.return_value = json.dumps(explicit['labels'])
        prediction = self.classify(record_id)
        append_review(prediction['attempt_id'], explicit['labels'], 'test-reviewer', 'Exact brand-link evidence', self.db)
        synthetic_id = self.add_record(explicit)
        self.classify(synthetic_id)
        classify_synthetic_fixture(synthetic_id, self.db)
        metrics = evaluate_research(self.db)
        self.assertEqual(metrics['eligible_predictions'], 1)
        self.assertEqual(metrics['explicit_spillover']['support'], 1)
        self.assertEqual(metrics['explicit_spillover']['f1'], 1)

    def test_rule_test_method_cannot_be_saved_on_real_record(self):
        from src.analysis.storage import append_attempt, load_eligible_record
        record_id = self.add_record(synthetic=False)
        self.permit(record_id)
        record = load_eligible_record(record_id, self.db)
        with self.assertRaises(ValueError):
            append_attempt(record, method='rule_based_test', status='success', labels=self.case['labels'],
                raw_output=None, error=None, metadata=self.client.inspect.return_value,
                prompt_version='test', needs_review=True, db_path=self.db)
        self.assertEqual(get_history(record_id, self.db)['attempts'], [])

    def test_batch_continues_after_block_and_does_not_repeat_ids(self):
        allowed = self.add_record()
        blocked = self.add_record(synthetic=False)
        result = classify_batch([blocked, allowed, allowed], 'fixture:latest', db_path=self.db)
        self.assertEqual([row['status'] for row in result], ['blocked', 'success'])
        self.assertEqual(self.client.generate.call_count, 1)

    def test_changed_source_is_excluded_from_metrics_and_review(self):
        record_id = self.add_record(synthetic=False)
        self.permit(record_id)
        result = self.classify(record_id)
        conn = get_connection(self.db)
        try:
            with conn:
                conn.execute('UPDATE records SET text=? WHERE record_id=?', ('changed test input', record_id))
        finally:
            conn.close()
        self.assertEqual(research_predictions(self.db), [])
        with self.assertRaises(ValueError):
            append_review(result['attempt_id'], self.case['labels'], 'test', 'test', self.db)


class TestContagionEvaluation(unittest.TestCase):
    def test_explicit_one_vs_rest_metrics(self):
        result = binary_metrics(['explicit', 'explicit', 'none', 'none'], ['explicit', 'none', 'explicit', 'none'])
        for name in ('accuracy', 'precision', 'recall', 'f1'):
            self.assertEqual(result[name], 0.5)
        self.assertEqual([result[key] for key in ('tp', 'fp', 'fn', 'tn')], [1, 1, 1, 1])
        self.assertEqual(result['support'], 2)

    def test_zero_denominators_are_undefined_not_fabricated_accuracy(self):
        result = binary_metrics([], [])
        self.assertTrue(all(result[name] is None for name in ('accuracy', 'precision', 'recall', 'f1')))
        no_predictions = binary_metrics(['none'], ['explicit'])
        self.assertIsNone(no_predictions['precision'])
        self.assertEqual(no_predictions['recall'], 0)
        self.assertEqual(no_predictions['f1'], 0)
        absent_positive = binary_metrics(['none'], ['none'])
        self.assertIsNone(absent_positive['recall'])
        with self.assertRaises(ValueError):
            binary_metrics(['none'], [])

    def test_all_fields_multilabel_topics_and_confusion_counts(self):
        pairs = [(case['labels'], copy.deepcopy(case['labels'])) for case in examples()]
        result = evaluate_pairs(pairs)
        self.assertEqual(result['n'], len(examples()))
        self.assertEqual(result['explicit_spillover']['f1'], 1)
        self.assertEqual(result['fields']['sentiment']['accuracy'], 1)
        self.assertEqual(result['topics']['privacy']['f1'], 1)
        self.assertEqual(result['fields']['spillover']['confusion']['explicit']['none'], 0)
