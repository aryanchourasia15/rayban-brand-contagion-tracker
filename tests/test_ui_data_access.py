"""Regression checks for explorer filters and saving reviewed news snapshots."""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.data.db import init_db, insert_record, get_batches
from src.ui.data_access import load_records, load_history, import_news_preview


class TestCollectionAdapters(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'ui.db'
        init_db(self.path)

    def add_record(self, **overrides):
        record = dict(source='News', source_type='media', collection_method='GDELT',
                      text='Ray-Ban privacy evidence', title='News headline',
                      published_at='2026-11-01T23:59:59Z', collected_at='2026-11-02T12:00:00+00:00',
                      relevance_flag='relevant')
        record.update(overrides)
        return insert_record(record, db_path=self.path)

    def test_empty_database(self):
        self.assertTrue(load_records(db_path=self.path).empty)
        self.assertTrue(load_history(self.path).empty)

    def test_combined_filters_and_inclusive_dates_exclude_synthetic(self):
        real_id = self.add_record()
        self.add_record(is_synthetic=True)
        self.add_record(source='Reddit', source_type='customer_discussion', collection_method='API')
        self.add_record(published_at='2026-11-02T00:00:00Z')
        result = load_records(sources=['News'], source_types=['media'], relevance_flags=['relevant'],
                              search='PRIVACY', published_from=date(2026, 11, 1), published_to=date(2026, 11, 1),
                              collected_from=date(2026, 11, 2), collected_to=date(2026, 11, 2), db_path=self.path)
        self.assertEqual(result['record_id'].tolist(), [real_id])
        self.assertEqual(len(load_records(db_path=self.path)), 3)
        self.assertTrue(load_records(search="' OR 1=1 --", db_path=self.path).empty)
        self.assertTrue(load_records(search='%', db_path=self.path).empty)

    def test_confirmed_preview_import_is_idempotent_and_audited(self):
        from src.data.connectors.gdelt import transform_gdelt_article_to_record
        original = 'Reviewed Ray-Ban Meta privacy headline'
        record = transform_gdelt_article_to_record(
            dict(title=original, url='https://example.com/article', seendate='20261101T120000Z'), 'test')
        with patch('requests.Session.get', side_effect=AssertionError('Preview import must not fetch')):
            first = import_news_preview([record], 'test', invalid_count=1, db_path=self.path)
            second = import_news_preview([record], 'test', db_path=self.path)
        self.assertEqual(first, {'imported': 1, 'duplicates': 0, 'invalid': 1})
        self.assertEqual(second, {'imported': 0, 'duplicates': 1, 'invalid': 0})
        stored = load_records(db_path=self.path)
        self.assertEqual(stored.iloc[0]['text'], original)
        history = load_history(self.path)
        self.assertEqual(len(history), 2)
        self.assertIn('partial', history['status'].tolist())
        self.assertEqual(history['records_processed'].sum(), 3)

    def test_failed_snapshot_import_is_rolled_back_and_audited(self):
        records = [dict(source='News', source_type='media', collection_method='GDELT', text='')]
        with self.assertRaises(ValueError):
            import_news_preview(records, 'test', db_path=self.path)
        self.assertTrue(load_records(db_path=self.path).empty)
        batch = get_batches(db_path=self.path)[0]
        self.assertEqual(batch['status'], 'failed')
        self.assertIn('empty', batch['error_details'])

    def test_synthetic_batches_are_excluded_from_history(self):
        from src.data.db import start_batch
        start_batch('News', 'GDELT', is_synthetic=True, db_path=self.path)
        self.assertTrue(load_history(self.path).empty)

