"""
Unit tests for Module 4: GDELT News Connector (Mocked HTTP API, Parsing, Date Validation, Deduplication, and Batch Tracking).
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from src.data.connectors.gdelt import (
    fetch_gdelt_articles,
    format_gdelt_datetime,
    import_gdelt,
    preview_gdelt,
    search_gdelt,
    transform_gdelt_article_to_record,
    validate_gdelt_dates,
)
from src.data.db import get_connection, get_database_summary, init_db


class TestGDELTConnector(unittest.TestCase):
    def setUp(self):
        """Create an isolated temporary SQLite database for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_gdelt.db"
        init_db(self.db_path)

        # Sample mock GDELT API response
        self.mock_articles_data = {
            "articles": [
                {
                    "url": "https://www.reuters.com/technology/ray-ban-meta-glasses-privacy-probe-2024-03-10/",
                    "title": "Regulators Examine Ray-Ban Meta Smart Glasses Over Privacy Concerns",
                    "seendate": "20240310T150000Z",
                    "domain": "reuters.com",
                    "language": "English",
                    "sourcecountry": "United States",
                },
                {
                    "url": "https://techcrunch.com/2024/03/12/smart-glasses-surveillance-debate/",
                    "title": "Smart Glasses Rekindle Public Surveillance Debate",
                    "seendate": "20240312T093000Z",
                    "domain": "techcrunch.com",
                    "language": "English",
                    "sourcecountry": "United States",
                },
            ]
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_format_and_validate_gdelt_dates_historical_warning(self):
        """Test formatting dates and warning when requested range exceeds GDELT's rolling 90-day window."""
        # Date within window (e.g. 10 days ago)
        recent_date = datetime.now(timezone.utc) - timedelta(days=10)
        start_fmt, _, warning = validate_gdelt_dates(start_date=recent_date)
        self.assertIsNotNone(start_fmt)
        self.assertIsNone(warning)

        # Date beyond 90 days (historical 2023)
        old_date = datetime(2023, 5, 1, tzinfo=timezone.utc)
        start_fmt_old, _, warning_old = validate_gdelt_dates(start_date=old_date)
        self.assertIsNotNone(start_fmt_old)
        self.assertIsNotNone(warning_old)
        self.assertIn("rolling ~90-day (~3 months) recent news window", warning_old)
        self.assertIn("2023–2026 must be imported via CSV/JSON", warning_old)

    @patch("src.data.connectors.gdelt.requests.Session.get")
    def test_successful_api_response_and_parsing(self, mock_get):
        """Test successful GDELT API fetch and canonical field extraction."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(self.mock_articles_data)
        mock_resp.json.return_value = self.mock_articles_data
        mock_get.return_value = mock_resp

        res = search_gdelt(query='"Ray-Ban Meta"')
        self.assertTrue(res["success"])
        self.assertEqual(res["total_found"], 2)
        self.assertEqual(len(res["articles"]), 2)

        # Test transformation into canonical record
        rec = transform_gdelt_article_to_record(res["articles"][0], query='"Ray-Ban Meta"')
        self.assertEqual(rec["source"], "News")
        self.assertEqual(rec["source_type"], "media")
        self.assertEqual(rec["collection_method"], "GDELT")
        self.assertEqual(rec["title"], "Regulators Examine Ray-Ban Meta Smart Glasses Over Privacy Concerns")
        self.assertEqual(rec["text"], rec["title"])
        self.assertEqual(rec["published_at"], "2024-03-10T15:00:00Z")
        self.assertEqual(rec["domain"], "reuters.com")
        self.assertEqual(rec["raw_payload"]["language"], "English")

    @patch("src.data.connectors.gdelt.requests.Session.get")
    def test_empty_results_handling(self, mock_get):
        """Test graceful handling of empty responses from GDELT."""
        # Empty text response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = ""
        mock_get.return_value = mock_resp

        res = search_gdelt(query="NonExistentQuery12345")
        self.assertTrue(res["success"])
        self.assertEqual(res["total_found"], 0)
        self.assertEqual(res["articles"], [])

    @patch("src.data.connectors.gdelt.requests.Session.get")
    def test_malformed_html_response_handling(self, mock_get):
        """Test graceful handling when GDELT returns HTML or non-JSON content."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>Error: Query rate exceeded</body></html>"
        mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", mock_resp.text, 0)
        mock_get.return_value = mock_resp

        res = search_gdelt(query='"Ray-Ban Meta"')
        self.assertFalse(res["success"])
        self.assertIn("non-JSON response", res["error"])

    @patch("src.data.connectors.gdelt.requests.Session.get")
    def test_network_failure_and_retries(self, mock_get):
        """Test network errors trigger retries with backoff and report error on exhaustion."""
        mock_get.side_effect = requests.ConnectionError("Connection aborted")

        res = fetch_gdelt_articles(query='"Ray-Ban Meta"', max_retries=2, backoff_factor=0.01)
        self.assertFalse(res["success"])
        self.assertIn("Connection aborted", res["error"])
        # Verified 2 retries were attempted
        self.assertEqual(mock_get.call_count, 2)

    @patch("src.data.connectors.gdelt.requests.Session.get")
    def test_preview_gdelt(self, mock_get):
        """Test preview functionality returning transformed records without DB insertion."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(self.mock_articles_data)
        mock_resp.json.return_value = self.mock_articles_data
        mock_get.return_value = mock_resp

        preview = preview_gdelt(query='"Ray-Ban Meta"', max_records=1)
        self.assertTrue(preview["success"])
        self.assertEqual(len(preview["preview_records"]), 1)
        self.assertEqual(preview["preview_records"][0]["source"], "News")

    @patch("src.data.connectors.gdelt.requests.Session.get")
    def test_import_gdelt_end_to_end_and_duplicate_handling(self, mock_get):
        """Test atomic GDELT news ingestion and duplicate detection on repeated calls."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(self.mock_articles_data)
        mock_resp.json.return_value = self.mock_articles_data
        mock_get.return_value = mock_resp

        # 1st Ingestion: imports both articles
        res1 = import_gdelt(
            query='"Ray-Ban Meta"',
            is_synthetic=True,
            db_path=self.db_path,
        )
        self.assertTrue(res1["success"])
        self.assertEqual(res1["imported"], 2)
        self.assertEqual(res1["duplicates"], 0)

        # 2nd Ingestion of identical articles: 0 imported, 2 duplicates logged
        res2 = import_gdelt(
            query='"Ray-Ban Meta"',
            is_synthetic=True,
            db_path=self.db_path,
        )
        self.assertTrue(res2["success"])
        self.assertEqual(res2["imported"], 0)
        self.assertEqual(res2["duplicates"], 2)

        # Check DB summary
        summary = get_database_summary(include_synthetic=True, db_path=self.db_path)
        self.assertEqual(summary["total_records"], 2)
        self.assertEqual(summary["media_records"], 2)
        self.assertEqual(summary["total_duplicates_logged"], 2)

        # Check batch history
        conn = get_connection(self.db_path)
        try:
            batches = conn.execute("SELECT * FROM import_batches ORDER BY started_at ASC;").fetchall()
            self.assertEqual(len(batches), 2)
            self.assertEqual(batches[0]["status"], "completed")
            self.assertEqual(batches[0]["records_imported"], 2)
            self.assertEqual(batches[1]["status"], "completed")
            self.assertEqual(batches[1]["records_duplicate"], 2)
        finally:
            conn.close()

    @patch("src.data.connectors.gdelt.requests.Session.get")
    def test_import_gdelt_failed_batch_recorded_on_network_error(self, mock_get):
        """Test failed GDELT call marks batch as failed in DB."""
        mock_get.side_effect = requests.RequestException("GDELT Down")

        with self.assertRaises(RuntimeError):
            import_gdelt(
                query='"Ray-Ban Meta"',
                max_records=10,
                db_path=self.db_path,
            )

        conn = get_connection(self.db_path)
        try:
            batch = conn.execute("SELECT * FROM import_batches ORDER BY started_at DESC LIMIT 1;").fetchone()
            self.assertIsNotNone(batch)
            self.assertEqual(batch["status"], "failed")
            self.assertIn("GDELT Down", batch["error_details"])
        finally:
            conn.close()

    def test_date_validation_rejects_invalid_and_order_and_converts_tz(self):
        """Regression test 1: Explicit date validation, timezone conversion to UTC, and start > end rejection."""
        # 1. Invalid date explicitly raises ValueError
        with self.assertRaises(ValueError):
            format_gdelt_datetime("not-a-valid-date-xyz")

        with self.assertRaises(ValueError):
            validate_gdelt_dates(start_date="invalid_date_abc")

        # 2. Timezone-aware date is converted to UTC before formatting
        tz_plus_2 = timezone(timedelta(hours=2))
        dt_aware = datetime(2024, 3, 15, 16, 30, 0, tzinfo=tz_plus_2)
        formatted_utc = format_gdelt_datetime(dt_aware)
        self.assertEqual(formatted_utc, "20240315143000")

        # 3. start_date > end_date is explicitly rejected
        with self.assertRaises(ValueError):
            validate_gdelt_dates(start_date="2024-03-20", end_date="2024-03-10")

    @patch("src.data.connectors.gdelt.requests.Session.get")
    def test_unsupported_historical_request_rejected_before_api_call(self, mock_get):
        """Regression test 2: Historical dates pre-dating rolling ~90 days rejected without making API call."""
        old_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        res = fetch_gdelt_articles(query='"Ray-Ban Meta"', start_date=old_date)

        self.assertFalse(res["success"])
        # Verified no network API call was attempted
        self.assertEqual(mock_get.call_count, 0)
        self.assertIn("Unsupported historical request", res["error"])
        self.assertIn("Please import historical records (2023–2026) using the CSV/JSON importer", res["error"])

    @patch("src.data.connectors.gdelt.requests.Session.get")
    def test_unparseable_publication_dates_rejected_and_counted(self, mock_get):
        articles = [dict(title='Ray-Ban privacy', url=f'https://example.com/{index}', seendate=date)
                    for index, date in enumerate(['nonsense', '20240230T120000Z', None, '', '20240315T120000Z'])]
        for article in articles[:-1]:
            self.assertIsNone(transform_gdelt_article_to_record(article, query='test'))
        response = MagicMock(status_code=200)
        response.text = json.dumps({'articles': articles})
        response.json.return_value = {'articles': articles}
        mock_get.return_value = response
        result = import_gdelt(query='test', db_path=self.db_path)
        self.assertEqual((result['processed'], result['imported'], result['invalid']), (5, 1, 4))
        conn = get_connection(self.db_path)
        try:
            record = conn.execute('SELECT source_type, published_at FROM records').fetchone()
            self.assertEqual(tuple(record), ('media', '2024-03-15T12:00:00Z'))
            batch = conn.execute('SELECT status, records_invalid FROM import_batches').fetchone()
            self.assertEqual(tuple(batch), ('partial', 4))
        finally:
            conn.close()

    @patch("src.data.connectors.gdelt.requests.Session.get")
    def test_article_validation_requires_title_and_http_url(self, mock_get):
        """Regression test 3: Rejects malformed articles and reports them in import statistics."""
        # Test unit transformation
        # Missing title
        self.assertIsNone(transform_gdelt_article_to_record({"title": "", "url": "https://example.com/1"}, query="test"))
        # Missing URL
        self.assertIsNone(transform_gdelt_article_to_record({"title": "Valid Title", "url": ""}, query="test"))
        # Non-HTTP URL
        self.assertIsNone(transform_gdelt_article_to_record({"title": "Valid Title", "url": "ftp://example.com/1"}, query="test"))
        # Malformed URL
        self.assertIsNone(transform_gdelt_article_to_record({"title": "Valid Title", "url": "not a url :::"}, query="test"))

        # Test end-to-end import with 1 valid and 2 malformed articles
        batch_articles = {
            "articles": [
                {
                    "title": "Legitimate News Article on Smart Glasses",
                    "url": "https://reuters.com/article/legit",
                    "seendate": "20240315T120000Z",
                    "domain": "reuters.com",
                },
                {
                    "title": "",  # malformed: empty title
                    "url": "https://reuters.com/article/empty-title",
                },
                {
                    "title": "Article with Invalid URL",
                    "url": "ftp://malformed-protocol.com/test",  # malformed: non-http
                },
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(batch_articles)
        mock_resp.json.return_value = batch_articles
        mock_get.return_value = mock_resp

        res = import_gdelt(query='"smart glasses"', is_synthetic=True, db_path=self.db_path)
        self.assertTrue(res["success"])
        self.assertEqual(res["processed"], 3)
        self.assertEqual(res["imported"], 1)
        self.assertEqual(res["invalid"], 2)

        # Verify DB batch record contains invalid count
        conn = get_connection(self.db_path)
        try:
            batch = conn.execute("SELECT * FROM import_batches WHERE batch_id = ?;", (res["batch_id"],)).fetchone()
            self.assertEqual(batch["records_imported"], 1)
            self.assertEqual(batch["records_invalid"], 2)
            self.assertEqual(batch["status"], "partial")
        finally:
            conn.close()

    @patch("src.data.connectors.gdelt.requests.Session.get")
    def test_relevance_classification_integration_populates_sqlite_and_preserves_records(self, mock_get):
        """
        Integration test: Relevance classifier connects to GDELT ingestion.
        - relevance_flag is populated in SQLite records table with relevant/contextual/irrelevant.
        - All records are preserved in SQLite regardless of their classification (heuristic, not validated AI).
        """
        articles_payload = {
            "articles": [
                {
                    "title": "Ray-Ban Meta smart glasses spark privacy controversy over secret recording",
                    "url": "https://www.reuters.com/tech/ray-ban-meta-privacy-backlash",
                    "seendate": "20240315T120000Z",
                    "domain": "reuters.com",
                },
                {
                    "title": "Ray-Ban Meta smart glasses holiday sales and tech specs update",
                    "url": "https://www.theverge.com/wearables/ray-ban-meta-holiday-sales",
                    "seendate": "20240316T140000Z",
                    "domain": "theverge.com",
                },
                {
                    "title": "Best 10 holiday gifts for tech enthusiasts this year",
                    "url": "https://digitaltrends.com/gifts/holiday-guide-2024",
                    "seendate": "20240317T090000Z",
                    "domain": "digitaltrends.com",
                },
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(articles_payload)
        mock_resp.json.return_value = articles_payload
        mock_get.return_value = mock_resp

        # Run GDELT ingestion
        res = import_gdelt(query='"Ray-Ban Meta"', is_synthetic=True, db_path=self.db_path)
        self.assertTrue(res["success"])
        # All 3 records must be preserved regardless of classification (no records dropped)
        self.assertEqual(res["imported"], 3)
        self.assertEqual(res["duplicates"], 0)
        self.assertEqual(res["invalid"], 0)

        # Inspect SQLite records table
        conn = get_connection(self.db_path)
        try:
            records = conn.execute(
                "SELECT title, canonical_url, relevance_flag FROM records WHERE import_batch_id = ? ORDER BY rowid ASC;",
                (res["batch_id"],),
            ).fetchall()
            self.assertEqual(len(records), 3)

            # Record 1: Relevant (product + privacy controversy)
            self.assertEqual(records[0]["relevance_flag"], "relevant")
            self.assertIn("privacy controversy", records[0]["title"])

            # Record 2: Contextual (product mention without privacy controversy)
            self.assertEqual(records[1]["relevance_flag"], "contextual")
            self.assertIn("holiday sales", records[1]["title"])

            # Record 3: Irrelevant (general gift guide)
            self.assertEqual(records[2]["relevance_flag"], "irrelevant")
            self.assertIn("holiday gifts", records[2]["title"])

            # Ensure all values conform to the allowed vocabulary
            from src.config import VALID_RELEVANCE_FLAGS
            for rec in records:
                self.assertIn(rec["relevance_flag"], VALID_RELEVANCE_FLAGS)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
