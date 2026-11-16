"""Mocked Guardian protocol tests. Fixtures are synthetic and never touch research storage."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

from src.data.connectors import guardian
from src.data.db import init_db, get_connection, get_database_summary, get_batches


def article(index=1):
    return {'id': f'technology/2024/fixture-{index}', 'type': 'article',
            'webTitle': f'Synthetic Ray-Ban Meta privacy headline {index}',
            'webPublicationDate': '2024-03-15T12:00:00Z',
            'webUrl': f'https://www.theguardian.com/technology/2024/fixture-{index}',
            'fields': {'byline': 'Synthetic fixture', 'body': 'Must never be persisted',
                       'bodyText': 'Must never be persisted', 'publication': 'The Guardian'}}


def response(articles, page=1, pages=1, total=None, status=200):
    return MagicMock(status_code=status, json=lambda: {'response': {
        'status': 'ok', 'results': articles, 'currentPage': page, 'pages': pages,
        'total': len(articles) if total is None else total}})


@patch.object(guardian, 'GUARDIAN_ENABLED', True)
class TestGuardian(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'test.db'
        init_db(self.db)
        env = patch.dict(os.environ, GUARDIAN_API_KEY='test-secret-do-not-store',
                         GUARDIAN_PERMISSION_REFERENCE='test-permission-only')
        env.start()
        self.addCleanup(env.stop)
        guardian._daily_requests.clear()
        guardian._last_request = None
        sleeper = patch.object(guardian.time, 'sleep')
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)
        self.http = MagicMock()

    def preview(self, **kwargs):
        return guardian.preview_guardian('"Ray-Ban Meta"', '2023-01-01', '2026-12-31', session=self.http, **kwargs)

    def test_historical_pagination_and_maximum(self):
        self.http.get.side_effect = [response([article(i) for i in range(50)], pages=3, total=101),
                                    response([article(i) for i in range(50, 100)], page=2, pages=3, total=101)]
        result = self.preview(max_records=60)
        self.assertTrue(result['success'])
        self.assertEqual(len(result['preview_records']), 60)
        self.assertEqual(result['pages_fetched'], 2)
        self.assertEqual(result['next_page'], 2)
        self.assertTrue(result['partial_page'])
        params = [call.kwargs['params'] for call in self.http.get.call_args_list]
        self.assertEqual([item['page'] for item in params], [1, 2])
        self.assertTrue(all(item['page-size'] == 50 for item in params))
        self.assertEqual(params[0]['from-date'], '2023-01-01')
        self.assertNotIn('body', params[0]['show-fields'])
        self.assertTrue(any(call.args[0] > 0 for call in self.sleep.call_args_list))
        self.assertEqual(get_database_summary(db_path=self.db)['total_records'], 0)

    def test_start_page_and_end_of_results(self):
        self.http.get.return_value = response([article()], page=3, pages=3, total=101)
        result = self.preview(start_page=3)
        self.assertTrue(result['success'])
        self.assertIsNone(result['next_page'])
        self.assertEqual(self.http.get.call_args.kwargs['params']['page'], 3)

    def test_missing_credentials_and_permission_make_no_request(self):
        for name in ('GUARDIAN_API_KEY', 'GUARDIAN_PERMISSION_REFERENCE'):
            with self.subTest(name=name), patch.dict(os.environ, {name: ''}):
                self.assertFalse(self.preview()['success'])
        self.http.get.assert_not_called()

    def test_authentication_and_quota_errors_are_sanitized(self):
        for status in (401, 403, 429, 400):
            with self.subTest(status=status):
                self.http.get.return_value = response([], status=status)
                result = self.preview()
                self.assertFalse(result['success'])
                self.assertIn(str(status), result['error'])
                self.assertNotIn('test-secret', json.dumps(result))
        self.assertEqual(self.http.get.call_count, 4)

    def test_network_error_does_not_expose_credential_url(self):
        self.http.get.side_effect = requests.ConnectionError('https://host/?api-key=test-secret-do-not-store')
        result = self.preview()
        self.assertFalse(result['success'])
        self.assertNotIn('test-secret', json.dumps(result))

    def test_server_retries_are_bounded(self):
        self.http.get.side_effect = [response([], status=503), response([article()])]
        self.assertTrue(self.preview()['success'])
        self.assertEqual(self.http.get.call_count, 2)
        self.assertIn(unittest.mock.call(1), self.sleep.call_args_list)

    def test_malformed_response_and_pagination(self):
        for data in ({}, {'response': {'status': 'ok', 'results': None}},
                     {'response': {'status': 'ok', 'results': [], 'currentPage': 5, 'pages': 1, 'total': 0}}):
            with self.subTest(data=data):
                self.http.get.return_value = MagicMock(status_code=200, json=lambda: data)
                self.assertFalse(self.preview()['success'])

    def test_invalid_dates_and_limits_make_no_request(self):
        for kwargs in ({'start_date': 'bad'}, {'start_date': '2026-01-01', 'end_date': '2023-01-01'},
                       {'max_records': 0}, {'start_page': 0}):
            with self.subTest(kwargs=kwargs):
                self.assertFalse(guardian.preview_guardian('query', session=self.http, **kwargs)['success'])
        self.http.get.assert_not_called()

    def test_metadata_validation_preserves_headline_and_excludes_bodies(self):
        raw = article()
        raw['webTitle'] = '  ' + raw['webTitle'] + '  '
        raw['apiUrl'] = 'https://host/?api-key=test-secret-do-not-store'
        record = guardian.transform_guardian_article_to_record(raw, 'query')
        self.assertEqual(record['text'], raw['webTitle'])
        self.assertEqual(record['raw_payload']['content_scope'], 'headline_only')
        self.assertEqual(record['raw_payload']['publisher'], 'The Guardian')
        self.assertEqual(record['source_type'], 'media')
        self.assertNotIn('body', json.dumps(record))
        self.assertNotIn('test-secret', json.dumps(record))
        for updates in ({'webTitle': ''}, {'id': None}, {'webUrl': 'bad'}, {'webPublicationDate': 'bad'}):
            with self.subTest(updates=updates):
                self.assertIsNone(guardian.transform_guardian_article_to_record({**raw, **updates}, 'query'))

    def test_preview_import_duplicates_and_provenance(self):
        self.http.get.return_value = response([article(), article(), {**article(2), 'webPublicationDate': 'bad'}])
        preview = self.preview()
        self.assertEqual(preview['invalid_count'], 1)
        with patch('requests.Session.get', side_effect=AssertionError('Must not refetch')):
            first = guardian.import_guardian_preview(preview, self.db)
            second = guardian.import_guardian_preview(preview, self.db)
        self.assertEqual((first['imported'], first['duplicates'], first['invalid']), (1, 1, 1))
        self.assertEqual((second['imported'], second['duplicates']), (0, 2))
        batch = get_batches(db_path=self.db)[0]
        self.assertEqual(batch['collection_method'], 'Guardian API')
        self.assertEqual(batch['status'], 'partial')
        conn = get_connection(self.db)
        try:
            record = dict(conn.execute('SELECT * FROM records').fetchone())
            self.assertEqual(record['collection_method'], 'Guardian API')
            self.assertEqual(record['source'], 'News')
            payload = json.loads(record['raw_payload'])
            self.assertEqual(payload['permission_reference'], 'test-permission-only')
            self.assertEqual(payload['from_date'], '2023-01-01')
            self.assertNotIn('test-secret', record['raw_payload'])
        finally:
            conn.close()

    def test_cross_connector_url_deduplication(self):
        from src.data.deduplicator import DeduplicationEngine
        raw = article()
        DeduplicationEngine(self.db).ingest_batch_safely([dict(
            source='News', source_type='media', collection_method='GDELT',
            text=raw['webTitle'], original_url=raw['webUrl'])])
        self.http.get.return_value = response([raw])
        result = guardian.import_guardian_preview(self.preview(), self.db)
        self.assertEqual((result['imported'], result['duplicates']), (0, 1))

    def test_failed_ingestion_tracks_failed_batch(self):
        self.http.get.return_value = response([article()])
        preview = self.preview()
        with patch.object(guardian.DeduplicationEngine, 'ingest_batch_safely', side_effect=RuntimeError('private details')):
            with self.assertRaises(RuntimeError):
                guardian.import_guardian_preview(preview, self.db)
        batch = get_batches(db_path=self.db)[0]
        self.assertEqual(batch['status'], 'failed')
        self.assertNotIn('private details', batch['error_details'])

    def test_empty_results_and_import_requires_reviewable_snapshot(self):
        self.http.get.return_value = response([], pages=0)
        preview = self.preview()
        self.assertTrue(preview['success'])
        with self.assertRaises(ValueError):
            guardian.import_guardian_preview(preview, self.db)

    def test_daily_budget_stops_before_http_request(self):
        from datetime import datetime, timezone
        import hashlib
        budget = (datetime.now(timezone.utc).date().isoformat(),
                  hashlib.sha256(b'test-secret-do-not-store').hexdigest())
        guardian._daily_requests[budget] = 500
        self.assertFalse(self.preview()['success'])
        self.http.get.assert_not_called()


class TestGuardianDisabled(unittest.TestCase):
    def test_default_block_prevents_requests_and_configuration_access(self):
        self.assertFalse(guardian.GUARDIAN_ENABLED)
        with patch.object(guardian.os, 'getenv', side_effect=AssertionError('Must not read credentials')), \
             patch.object(guardian.requests.Session, 'get', side_effect=AssertionError('No live request')):
            result = guardian.preview_guardian('Ray-Ban Meta')
            self.assertFalse(result['success'])
            self.assertIn('disabled', result['error'])
            self.assertEqual(result['preview_records'], [])

    def test_import_and_low_level_request_are_blocked(self):
        with patch.object(guardian, 'start_batch') as start:
            with self.assertRaisesRegex(ValueError, 'disabled'):
                guardian.import_guardian_preview({'success': True, 'preview_records': []})
            start.assert_not_called()
        session = MagicMock()
        with self.assertRaisesRegex(RuntimeError, 'disabled'):
            guardian._request(session, {}, '')
        session.get.assert_not_called()
