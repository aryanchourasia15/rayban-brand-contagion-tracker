"""Preflight tests use the existing synthetic fixtures, never research data."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.check_dataset_quality import check_dataset
from src.data.db import get_connection, init_db, insert_record
from src.data.importers.file_importer import detect_column_mapping, parse_file_to_rows


class TestDatasetQuality(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixtures = Path(__file__).parent / 'fixtures' / 'synthetic_records.json'
        self.fixtures = json.loads(fixtures.read_text(encoding='utf-8'))

    def write_rows(self, rows):
        path = self.root / 'input.json'
        path.write_text(json.dumps(rows), encoding='utf-8')
        return path

    def fixture_row(self, index=0):
        record = dict(self.fixtures[index])
        record['url'] = record.pop('original_url')
        record['origin_platform'] = record['source']
        return record

    def test_missing_metadata_invalid_rows_and_source_identification(self):
        row = self.fixture_row()
        row.update(url='', published_at='', source='', source_type='')
        invalid = self.fixture_row()
        invalid['url'] = 'not a URL'
        report = check_dataset(self.write_rows([row, invalid, None]))
        self.assertEqual(report['total_rows'], 3)
        issues = report['rows'][0]['issues']
        for issue in ('missing_source_url', 'missing_publication_date',
                      'missing_source_identification', 'missing_source_type'):
            self.assertIn(issue, issues)
        self.assertIn('Invalid URL', report['rows'][1]['validation_errors'][0])
        self.assertIn('invalid_row', report['rows'][2]['issues'])

    def test_within_file_duplicates_are_reproducible(self):
        row = self.fixture_row()
        path = self.write_rows([row, row])
        first = check_dataset(path)
        self.assertEqual(first, check_dataset(path))
        self.assertEqual(first['counts']['duplicate'], 1)
        self.assertEqual(first['rows'][1]['duplicate']['reason'], 'source_id')
        self.assertTrue(first['rows'][1]['duplicate']['matched_record_id'].endswith('_1'))

    def test_existing_database_duplicate_check_does_not_write(self):
        database = self.root / 'existing.db'
        init_db(database)
        insert_record(dict(self.fixtures[0]), db_path=database)
        before = database.read_bytes()
        report = check_dataset(self.write_rows([self.fixture_row(), self.fixture_row(1)]), database)
        self.assertEqual(report['counts']['duplicate'], 1)
        self.assertEqual(report['rows'][0]['duplicate']['matched_record_id'], self.fixtures[0]['record_id'])
        self.assertEqual(database.read_bytes(), before)
        conn = get_connection(database)
        try:
            for table, expected in [('records', 1), ('import_batches', 0), ('duplicate_audit', 0)]:
                self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], expected)
        finally:
            conn.close()

    def test_headline_collision_protection_and_relevance_reporting(self):
        row = self.fixture_row(1)
        row['source_id'] = None
        other = dict(row, url=self.fixtures[0]['original_url'])
        irrelevant = dict(row, text='', title='', url='', source_id=None)
        # Empty source text is rejected rather than classified as genuine evidence.
        report = check_dataset(self.write_rows([row, other, irrelevant]))
        self.assertNotIn('duplicate', report['counts'])
        self.assertIn(report['rows'][0]['relevance_flag'], ('relevant', 'contextual', 'irrelevant'))
        self.assertIn('invalid_row', report['rows'][2]['issues'])

    def test_templates_have_only_headers_and_match_importer(self):
        templates = Path(__file__).resolve().parents[1] / 'templates'
        for name in ('reddit_records.csv', 'youtube_comments.csv', 'historical_news.csv'):
            with self.subTest(name=name):
                rows, headers = parse_file_to_rows(templates / name)
                self.assertEqual(rows, [])
                mapping = detect_column_mapping(headers)
                for field in ('text', 'url', 'source', 'source_type', 'source_id', 'published_at'):
                    self.assertEqual(mapping[field], field)
                self.assertIn('permission_reference', headers)
        missing = self.root / 'missing.db'
        with self.assertRaises(ValueError):
            check_dataset(self.write_rows([self.fixture_row()]), missing)
        self.assertFalse(missing.exists())

    def test_relevance_is_reported_without_discarding_irrelevant_rows(self):
        relevant = self.fixture_row()
        contextual = dict(relevant, source_id=None, title=None, url=None, text='privacy')
        irrelevant = dict(contextual, text=self.fixtures[0]['text'].split()[0])
        report = check_dataset(self.write_rows([relevant, contextual, irrelevant]))
        self.assertEqual([row['relevance_flag'] for row in report['rows']],
                         ['relevant', 'contextual', 'irrelevant'])
        self.assertEqual(report['counts']['relevance_irrelevant'], 1)
        self.assertIn('review_relevance', report['rows'][2]['issues'])
        self.assertEqual(report['total_rows'], 3)

