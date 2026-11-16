"""Dashboard calculations and filters on synthetic fixture labels, never research findings."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.analysis.storage import init_analysis_db, record_permission, append_review
from src.analysis.engine import classify_record
from src.analysis.ollama_client import local_model_status, LocalModelError
from src.data.db import get_connection, insert_record
from src.ui.contagion_data import (
    demo_discussions, select_label_basis, spillover_rate, filter_discussions,
    sentiment_comparison, spillover_trends, highlighted_evidence,
    approved_discussions, classified_discussions,
)


class TestContagionDashboardCalculations(unittest.TestCase):
    def setUp(self):
        self.raw = demo_discussions()
        self.rows = select_label_basis(self.raw)

    def test_spillover_cohort_and_small_sample_rule(self):
        report = spillover_rate(self.rows)
        self.assertEqual(report['explicit'], 1)
        self.assertIsNone(report['percent'])
        self.assertGreater(report['denominator'], report['explicit'])
        one = copy.deepcopy(next(row for row in self.rows if row['prediction']['spillover'] == 'explicit'))
        other = copy.deepcopy(one)
        other['active_labels']['sentiment'] = 'mixed'
        nonprivacy = copy.deepcopy(one)
        nonprivacy['active_labels']['topic'] = ['technology']
        self.assertEqual(spillover_rate([other, nonprivacy])['denominator'], 0)
        enough = spillover_rate([copy.deepcopy(one) for _ in range(20)])
        self.assertEqual(enough['percent'], 100)
        self.assertEqual(spillover_rate([]), dict(explicit=0, denominator=0, percent=None))

    def test_combined_filters_case_insensitive_search_and_any_topic(self):
        result = filter_discussions(self.rows, search='TRADITIONAL', sentiments=['positive'],
                                    topics=['privacy', 'fashion'], targets=['core Ray-Ban'], spillovers=['none'])
        self.assertEqual([row['record_id'] for row in result], ['demo:positive_core'])
        self.assertEqual(filter_discussions(self.rows, search='not present in fixture'), [])

    def test_human_basis_never_silently_uses_ai_labels(self):
        raw = copy.deepcopy(self.raw)
        self.assertEqual(select_label_basis(raw, 'Human-reviewed labels'), [])
        raw[0]['human_labels'] = {**raw[0]['prediction'], 'sentiment': 'neutral'}
        result = select_label_basis(raw, 'Human-reviewed labels')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['active_labels']['sentiment'], 'neutral')
        self.assertEqual(raw[0]['prediction']['sentiment'], 'negative')
        self.assertNotIn('active_labels', raw[0])

    def test_flagged_review_filter_excludes_already_reviewed(self):
        self.rows[0]['human_labels'] = self.rows[0]['prediction']
        result = filter_discussions(self.rows, review_only=True)
        self.assertNotIn(self.rows[0]['record_id'], [row['record_id'] for row in result])
        self.assertTrue(all(row['needs_review'] and row['human_labels'] is None for row in result))

    def test_sentiment_comparison_does_not_assign_both_to_two_targets(self):
        comparison = sentiment_comparison(self.rows)
        self.assertEqual(set(comparison['target']), {'Ray-Ban Meta', 'core Ray-Ban'})
        expected = sum(row['active_labels']['target'] in ('Ray-Ban Meta', 'core Ray-Ban') for row in self.rows)
        self.assertEqual(comparison['Records'].sum(), expected)
        self.assertTrue(sentiment_comparison([]).empty)

    def test_trends_by_year_and_source_handle_missing_dates(self):
        self.assertTrue(spillover_trends(self.rows).empty)
        rows = copy.deepcopy(self.rows[:3])
        rows[0].update(published_at='2023-01-01T00:00:00Z', source='Reddit')
        rows[1].update(published_at='2024-01-01T00:00:00Z', source='Imported')
        rows[2]['published_at'] = 'bad'
        result = spillover_trends(rows)
        self.assertEqual(set(result['year']), {'2023', '2024'})
        self.assertEqual(set(result['source']), {'Reddit', 'Imported'})
        self.assertEqual(result['Records'].sum(), 2)

    def test_evidence_highlighting_escapes_source_html_and_regex(self):
        text = '<script>alert(1)</script> Privacy & trust. Privacy & trust.'
        marked = highlighted_evidence(text, ['Privacy & trust.', 'invented evidence'])
        self.assertNotIn('<script>', marked)
        self.assertIn('&lt;script&gt;', marked)
        self.assertEqual(marked.count('<mark>'), 2)
        self.assertIn('Privacy &amp; trust.', marked)
        self.assertEqual(highlighted_evidence('<b>x</b>', []), '&lt;b&gt;x&lt;/b&gt;')

    def test_demo_is_detached_labelled_and_has_no_invented_urls_or_dates(self):
        self.assertTrue(all(row['demo'] and row['url'] is None and row['published_at'] is None for row in self.raw))
        self.raw[0]['prediction']['sentiment'] = 'neutral'
        self.assertEqual(demo_discussions()[0]['prediction']['sentiment'], 'negative')


class TestContagionDashboardAccess(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'dashboard.db'
        init_analysis_db(self.db)
        self.fixture = demo_discussions()[0]

    def record(self, **overrides):
        return insert_record(dict(source='Imported', source_type='customer_discussion', collection_method='CSV import',
                                  text=self.fixture['text']) | overrides, db_path=self.db)

    def test_only_real_approved_valid_customer_discussions_are_selectable(self):
        allowed = self.record()
        self.record()
        self.record(is_synthetic=True)
        self.record(source='News', source_type='media')
        self.record(status='invalid')
        record_permission(allowed, 'test-only-reference', 'test-verifier', verified=True, db_path=self.db)
        self.assertEqual([row['record_id'] for row in approved_discussions(self.db)], [allowed])
        record_permission(allowed, 'test-revocation', 'test-verifier', verified=True, revoke=True, db_path=self.db)
        self.assertEqual(approved_discussions(self.db), [])

    def test_research_data_adapter_preserves_prediction_and_review_separately(self):
        import json
        from unittest.mock import MagicMock
        record_id = self.record(published_at='2024-01-01T00:00:00Z', original_url='https://example.com/test')
        record_permission(record_id, 'test-only-reference', 'test-verifier', verified=True, db_path=self.db)
        client = MagicMock()
        client.inspect.return_value = dict(model_name='test:latest', model_version='test-digest', runtime_version='test-runtime')
        client.generate.return_value = json.dumps(self.fixture['prediction'])
        with patch('src.analysis.engine.OllamaClient', return_value=client):
            result = classify_record(record_id, 'test:latest', db_path=self.db)
        correction = {**self.fixture['prediction'], 'spillover': 'unclear'}
        append_review(result['attempt_id'], correction, 'test-reviewer', 'test reasoning', self.db)
        rows = classified_discussions(self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['prediction']['spillover'], 'none')
        self.assertEqual(rows[0]['human_labels']['spillover'], 'unclear')
        self.assertEqual(rows[0]['text'], self.fixture['text'])
        self.assertFalse(rows[0]['demo'])

    def test_demo_loading_does_not_write_any_database_records(self):
        demo_discussions()
        conn = get_connection(self.db)
        try:
            for table in ('records', 'classification_attempts', 'human_reviews', 'classification_permissions'):
                self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
        finally:
            conn.close()


class TestDashboardModelDiscovery(unittest.TestCase):
    def test_inventory_filters_cloud_stubs_and_does_not_infer_or_pull(self):
        from unittest.mock import MagicMock
        inventory = {'models': [
            dict(name='local:latest', size=100, digest='test'),
            dict(name='remote:cloud', size=100, digest='test'),
            dict(name='proxy:latest', size=100, digest='test', remote_host='https://example.com'),
            dict(name='missing:latest', size=0, digest='test')]}
        replies = [MagicMock(status_code=200, json=lambda: inventory),
                   MagicMock(status_code=200, json=lambda: {'version': 'test'})]
        with patch('requests.Session.request', side_effect=replies) as request:
            self.assertEqual(local_model_status(), {'version': 'test', 'models': ['local:latest']})
        self.assertEqual([call.args[0] for call in request.call_args_list], ['GET', 'GET'])
        self.assertTrue(all('127.0.0.1' in call.args[1] for call in request.call_args_list))

    def test_connection_failure_is_reported_without_cloud_fallback(self):
        import requests
        with patch('requests.Session.request', side_effect=requests.ConnectionError('test offline')) as request:
            with self.assertRaises(LocalModelError):
                local_model_status()
        self.assertEqual(request.call_count, 1)
