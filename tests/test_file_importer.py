"""
Unit tests for Module 3: CSV & JSON Importer (Parsing, Auto-mapping, Validation, Idempotency, and Batch Tracking).
"""

import json
import csv
import io
import tempfile
import unittest
from datetime import timezone
from pathlib import Path

from src.data.db import get_connection, get_database_summary, init_db
from src.data.importers.file_importer import (
    detect_column_mapping,
    generate_csv_template,
    import_file,
    parse_file_to_rows,
    preview_import,
    validate_and_transform_rows,
)


class TestFileImporterModule(unittest.TestCase):
    def test_original_text_preserved_through_csv_and_json_ingestion(self):
        original = '  Trust &amp; Privacy\x00\u200b\nSecond\tline  '
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['body'])
        writer.writerow([original])
        for file_format, content in [('csv', output.getvalue()), ('json', json.dumps([{'body': original}]))]:
            with self.subTest(file_format=file_format):
                result = import_file(content, file_format=file_format, db_path=self.db_path)
                conn = get_connection(self.db_path)
                try:
                    record = conn.execute('SELECT * FROM records WHERE record_id = ?', (result['imported_ids'][0],)).fetchone()
                    self.assertEqual(record['text'], original)
                    self.assertEqual(record['normalized_text'], 'trust & privacy second line')
                    self.assertEqual(json.loads(record['raw_payload'])['body'], original)
                finally:
                    conn.close()

    def test_import_rejects_malformed_urls_with_row_errors(self):
        urls = ['not a URL', 'ftp://example.com/a', 'https://', 'https://bad..com/a',
                'https://example.com:99999/a', 'https://example.com/a b']
        for file_format in ('csv', 'json'):
            with self.subTest(file_format=file_format):
                rows = [{'text': 'Evidence', 'url': url} for url in urls]
                rows += [{'text': 'Valid evidence', 'url': 'example.com/article'}, {'text': 'No URL'}]
                if file_format == 'json':
                    content = json.dumps(rows)
                else:
                    output = io.StringIO()
                    writer = csv.DictWriter(output, fieldnames=['text', 'url'])
                    writer.writeheader()
                    writer.writerows(rows)
                    content = output.getvalue()
                result = import_file(content, file_format=file_format, db_path=self.db_path)
                self.assertEqual(result['invalid'], len(urls))
                self.assertEqual([error['row_number'] for error in result['errors']], list(range(1, len(urls) + 1)))
                self.assertTrue(all('Invalid URL' in error['errors'][0] for error in result['errors']))

    def test_platform_source_types_override_defaults_and_reject_conflicts(self):
        for source, expected, wrong in [('News', 'media', 'customer_discussion'),
                                        ('Reddit', 'customer_discussion', 'media')]:
            with self.subTest(source=source):
                result = import_file(json.dumps([{'text': 'Evidence', 'source': source}]),
                                     file_format='json', default_source_type=wrong, db_path=self.db_path)
                conn = get_connection(self.db_path)
                try:
                    record = conn.execute('SELECT source_type FROM records WHERE record_id = ?', (result['imported_ids'][0],)).fetchone()
                    self.assertEqual(record['source_type'], expected)
                finally:
                    conn.close()
                valid, invalid = validate_and_transform_rows([{'text': 'Evidence', 'source': source, 'source_type': wrong}])
                self.assertEqual(valid, [])
                self.assertIn('requires source_type', invalid[0]['errors'][0])

    def setUp(self):
        """Create an isolated temporary SQLite database for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_import.db"
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_detect_column_mapping_aliases(self):
        """Test automatic column detection for common aliases."""
        headers = ["Comment", "Headline", "Created_At", "Permalink", "Platform", "Upvotes"]
        mapping = detect_column_mapping(headers)

        self.assertEqual(mapping.get("text"), "Comment")
        self.assertEqual(mapping.get("title"), "Headline")
        self.assertEqual(mapping.get("published_at"), "Created_At")
        self.assertEqual(mapping.get("url"), "Permalink")
        self.assertEqual(mapping.get("source"), "Platform")
        # 'Upvotes' is unmapped
        self.assertNotIn("Upvotes", mapping.values())

    def test_parse_csv_utf8_with_bom(self):
        """Test parsing CSV with UTF-8 BOM encoding."""
        csv_content = "\ufefftext,title,published_at\n\"I love the audio on these glasses\",Great Audio,2024-03-15T14:00:00Z\n"
        bytes_input = csv_content.encode("utf-8-sig")

        rows, headers = parse_file_to_rows(bytes_input, file_format="csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "I love the audio on these glasses")
        self.assertIn("text", headers)

    def test_parse_json_formats(self):
        """Test parsing JSON array and wrapped objects (records, data)."""
        # 1. Plain array
        json_array = json.dumps([
            {"text": "Comment A", "title": "Title A"},
            {"text": "Comment B", "title": "Title B"},
        ])
        rows1, _ = parse_file_to_rows(json_array, file_format="json")
        self.assertEqual(len(rows1), 2)

        # 2. Wrapped {"records": [...]}
        json_wrapped = json.dumps({
            "records": [{"body": "Comment from wrapped JSON", "headline": "Headline 1"}],
            "metadata": {"version": "1.0"},
        })
        rows2, _ = parse_file_to_rows(json_wrapped, file_format="json")
        self.assertEqual(len(rows2), 1)
        self.assertEqual(rows2[0]["body"], "Comment from wrapped JSON")

    def test_validate_and_transform_rows_and_unmapped_payload(self):
        """Test row transformation, required validation, and preserving unmapped columns."""
        raw_rows = [
            {
                "comment": "I worry about bystander consent when wearing Ray-Ban Meta at the mall.",
                "headline": "Bystander Consent",
                "date": "2024-03-15T14:30:00Z",
                "link": "https://reddit.com/r/privacy/comments/999",
                "author": "john_doe",
                "upvotes": 52,
            },
            {
                # Missing required text
                "comment": "   ",
                "headline": "Empty Comment Row",
            },
        ]
        mapping = detect_column_mapping(["comment", "headline", "date", "link", "author", "upvotes"])

        valid, invalid = validate_and_transform_rows(raw_rows, column_mapping=mapping)

        # Row 1 is valid
        self.assertEqual(len(valid), 1)
        rec = valid[0]
        self.assertEqual(rec["text"], "I worry about bystander consent when wearing Ray-Ban Meta at the mall.")
        self.assertEqual(rec["title"], "Bystander Consent")
        self.assertEqual(rec["original_url"], "https://reddit.com/r/privacy/comments/999")
        self.assertEqual(rec["published_at"], "2024-03-15T14:30:00Z")

        # Unmapped columns (author, upvotes) preserved in raw_payload
        self.assertEqual(rec["raw_payload"].get("author"), "john_doe")
        self.assertEqual(rec["raw_payload"].get("upvotes"), 52)

        # Row 2 is invalid
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0]["row_number"], 2)
        self.assertIn("Missing or empty required field 'text'", invalid[0]["errors"][0])

    def test_validation_rejects_ambiguous_dates_without_rules(self):
        """Ambiguous dates without explicit rules must be rejected during validation."""
        raw_rows = [
            {
                "text": "Valid discussion comment about Ray-Ban Meta frames.",
                "published_at": "03/04/2024",  # ambiguous day/month
            }
        ]
        valid, invalid = validate_and_transform_rows(raw_rows, day_first=None, default_tz=None)
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(invalid), 1)
        self.assertIn("Invalid or ambiguous date format", invalid[0]["errors"][0])

        # Passing explicit day_first and default_tz succeeds
        valid2, invalid2 = validate_and_transform_rows(
            raw_rows,
            day_first=False,
            default_tz=timezone.utc,
        )
        self.assertEqual(len(valid2), 1)
        self.assertEqual(valid2[0]["published_at"], "2024-03-04T00:00:00Z")

    def test_preview_import(self):
        """Test preview functionality returning first N records and mappings."""
        csv_content = (
            "body,headline,date\n"
            "Review 1,Head 1,2024-03-15T10:00:00Z\n"
            "Review 2,Head 2,2024-03-15T11:00:00Z\n"
            "Review 3,Head 3,2024-03-15T12:00:00Z\n"
        )
        preview = preview_import(csv_content, n_preview=2)
        self.assertEqual(preview["total_rows_detected"], 3)
        self.assertEqual(preview["preview_valid_count"], 2)
        self.assertEqual(preview["detected_mapping"]["text"], "body")

    def test_import_file_end_to_end_and_idempotency(self):
        """Test end-to-end atomic file import and idempotent repeated imports."""
        csv_content = (
            "content,title,url,date\n"
            "\"I returned my Ray-Ban Meta glasses because the camera light is easily covered.\",Light Covered,https://example.com/r1,2024-03-15T10:00:00Z\n"
            "\"The smart glasses are stylish but people notice the cameras in indoor meetings.\",Indoor Meetings,https://example.com/r2,2024-03-15T11:00:00Z\n"
            "\"  \",Invalid Empty Text,https://example.com/r3,2024-03-15T12:00:00Z\n"
        )

        # 1st Import: 2 valid records imported, 1 invalid row rejected
        res1 = import_file(
            file_input=csv_content,
            file_format="csv",
            default_source="Imported",
            default_source_type="customer_discussion",
            is_synthetic=True,
            db_path=self.db_path,
        )

        self.assertTrue(res1["success"])
        self.assertEqual(res1["processed"], 3)
        self.assertEqual(res1["imported"], 2)
        self.assertEqual(res1["duplicates"], 0)
        self.assertEqual(res1["invalid"], 1)

        # Check database summary
        summary1 = get_database_summary(include_synthetic=True, db_path=self.db_path)
        self.assertEqual(summary1["total_records"], 2)

        # 2nd Import of identical content: 0 imported, 2 duplicates detected, 1 invalid row rejected
        res2 = import_file(
            file_input=csv_content,
            file_format="csv",
            default_source="Imported",
            default_source_type="customer_discussion",
            is_synthetic=True,
            db_path=self.db_path,
        )

        self.assertTrue(res2["success"])
        self.assertEqual(res2["imported"], 0)
        self.assertEqual(res2["duplicates"], 2)
        self.assertEqual(res2["invalid"], 1)

        # Total canonical records in database remains exactly 2 (idempotent)
        summary2 = get_database_summary(include_synthetic=True, db_path=self.db_path)
        self.assertEqual(summary2["total_records"], 2)
        self.assertEqual(summary2["total_duplicates_logged"], 2)

    def test_generate_csv_template(self):
        """Test downloadable CSV template generation."""
        template = generate_csv_template()
        self.assertIn("text,title,published_at,url,source,source_type,source_id,notes", template)
        # Parse template to ensure it is valid CSV
        rows, headers = parse_file_to_rows(template, file_format="csv")
        self.assertEqual(len(rows), 1)
        self.assertIn("text", headers)

    def test_malformed_json_raises_error(self):
        """Test graceful error handling for malformed JSON."""
        with self.assertRaises(ValueError):
            parse_file_to_rows("{ malformed json content ... }", file_format="json")

    def test_subreddit_metadata_mapping_identifies_reddit_source(self):
        """Regression test 1: Subreddit is metadata, not platform name; identifies Reddit as source."""
        raw_rows = [
            {
                "text": "Discussion on smart glasses in privacy forum.",
                "subreddit": "privacy",
                "upvotes": 42,
            }
        ]
        valid, invalid = validate_and_transform_rows(raw_rows)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["source"], "Reddit")
        self.assertEqual(valid[0]["raw_payload"]["subreddit"], "privacy")

    def test_non_object_json_entries_reported_as_invalid_rows(self):
        """Regression test 2: Non-object JSON items are reported as invalid rows with row numbers."""
        json_content = json.dumps([
            {"text": "Valid comment in object"},
            "this is just a string, not an object",
            12345,
            {"text": "Another valid comment"},
        ])
        rows, _ = parse_file_to_rows(json_content, file_format="json")
        self.assertEqual(len(rows), 4)

        valid, invalid = validate_and_transform_rows(rows)
        self.assertEqual(len(valid), 2)
        self.assertEqual(len(invalid), 2)
        self.assertEqual(invalid[0]["row_number"], 2)
        self.assertIn("not an object/dictionary", invalid[0]["errors"][0])
        self.assertEqual(invalid[1]["row_number"], 3)

    def test_complete_original_row_preserved_in_raw_payload(self):
        """Regression test 3: Complete original row (including mapped fields) preserved in raw_payload."""
        raw_rows = [
            {
                "text": "Original comment unmodified",
                "title": "Title mapped",
                "extra_field_1": "Custom value 1",
                "extra_field_2": 99,
            }
        ]
        valid, _ = validate_and_transform_rows(raw_rows)
        self.assertEqual(len(valid), 1)
        payload = valid[0]["raw_payload"]
        self.assertEqual(payload["text"], "Original comment unmodified")
        self.assertEqual(payload["title"], "Title mapped")
        self.assertEqual(payload["extra_field_1"], "Custom value 1")
        self.assertEqual(payload["extra_field_2"], 99)

    def test_ingestion_failure_marks_batch_as_failed_and_rolls_back(self):
        """Regression test 4: If ingestion fails, batch status is marked 'failed' and changes roll back."""
        from unittest.mock import patch

        csv_content = "text\n\"Valid comment that will hit mocked error\"\n"

        # Mock insert_records_atomic to simulate database error during ingestion
        with patch("src.data.importers.file_importer.DeduplicationEngine.ingest_batch_safely") as mock_ingest:
            mock_ingest.side_effect = RuntimeError("Simulated DB Disk Full")
            with self.assertRaises(RuntimeError):
                import_file(
                    file_input=csv_content,
                    file_format="csv",
                    db_path=self.db_path,
                )

        # Verify batch record in import_batches table
        conn = get_connection(self.db_path)
        try:
            batch = conn.execute("SELECT * FROM import_batches ORDER BY started_at DESC LIMIT 1;").fetchone()
            self.assertIsNotNone(batch)
            self.assertEqual(batch["status"], "failed")
            self.assertIn("Simulated DB Disk Full", batch["error_details"])

            # Verify collection_logs recorded error
            log = conn.execute("SELECT * FROM collection_logs WHERE batch_id = ? AND level = 'ERROR';", (batch["batch_id"],)).fetchone()
            self.assertIsNotNone(log)
            self.assertIn("Simulated DB Disk Full", log["message"])

            # Zero records inserted into records table
            count = conn.execute("SELECT COUNT(*) as cnt FROM records;").fetchone()["cnt"]
            self.assertEqual(count, 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
