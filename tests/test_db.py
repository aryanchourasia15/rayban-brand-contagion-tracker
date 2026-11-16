"""
Unit tests for Module 1: SQLite Database, Schema, Provenance, and Atomic Transactions.
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.data.db import (
    find_existing_record,
    finish_batch,
    get_connection,
    get_database_summary,
    get_record_by_id,
    init_db,
    insert_record,
    insert_records_atomic,
    log_event,
    record_duplicate,
    start_batch,
)


class TestDatabaseModule(unittest.TestCase):
    def test_source_type_constraints_at_storage_boundary(self):
        for source, method, wrong in [('News', 'CSV import', 'customer_discussion'),
                                      ('Reddit', 'API', 'media'),
                                      ('Imported', 'GDELT', 'customer_discussion')]:
            with self.subTest(source=source, method=method):
                with self.assertRaisesRegex(ValueError, 'requires source_type'):
                    insert_record({'source': source, 'source_type': wrong,
                                   'collection_method': method, 'text': 'Evidence'}, db_path=self.db_path)

    def test_synthetic_duplicate_and_latest_batch_metrics(self):
        real_batch = start_batch('Imported', 'CSV import', db_path=self.db_path)
        real_id = insert_record({'source': 'Imported', 'source_type': 'customer_discussion',
                                 'collection_method': 'CSV import', 'text': 'Real evidence',
                                 'import_batch_id': real_batch, 'collected_at': '2024-01-01T00:00:00Z'},
                                db_path=self.db_path)
        synthetic_batch = start_batch('Imported', 'CSV import', is_synthetic=True, db_path=self.db_path)
        synthetic_id = insert_record({'source': 'Imported', 'source_type': 'media',
                                      'collection_method': 'CSV import', 'text': 'Synthetic evidence',
                                      'is_synthetic': True, 'import_batch_id': synthetic_batch,
                                      'collected_at': '2030-01-01T00:00:00Z'}, db_path=self.db_path)
        # Real attempt, synthetic attempt in a real batch, synthetic batch,
        # and an unbatched attempt matching synthetic evidence.
        for batch, matched, synthetic in [(real_batch, real_id, False),
                                           (real_batch, real_id, True),
                                           (synthetic_batch, real_id, False),
                                           (None, synthetic_id, False)]:
            record_duplicate(batch, matched, 'canonical_url', is_synthetic=synthetic, db_path=self.db_path)
        conn = get_connection(self.db_path)
        try:
            with conn:
                conn.execute('UPDATE import_batches SET started_at = ? WHERE batch_id = ?', ('2024-01-01', real_batch))
                conn.execute('UPDATE import_batches SET started_at = ? WHERE batch_id = ?', ('2030-01-01', synthetic_batch))
        finally:
            conn.close()
        clean = get_database_summary(db_path=self.db_path)
        self.assertEqual((clean['total_records'], clean['customer_discussions'], clean['media_records']), (1, 1, 0))
        self.assertEqual(clean['total_duplicates_logged'], 1)
        self.assertEqual(clean['latest_batch']['batch_id'], real_batch)
        self.assertEqual(clean['latest_collection_timestamp'], '2024-01-01T00:00:00Z')
        all_data = get_database_summary(include_synthetic=True, db_path=self.db_path)
        self.assertEqual(all_data['total_records'], 2)
        self.assertEqual(all_data['total_duplicates_logged'], 4)
        self.assertEqual(all_data['latest_batch']['batch_id'], synthetic_batch)
        self.assertEqual(all_data['latest_collection_timestamp'], '2030-01-01T00:00:00Z')

    def test_synthetic_only_metrics_and_audit_migration(self):
        batch = start_batch('Imported', 'CSV import', is_synthetic=True, db_path=self.db_path)
        record = dict(self.synthetic_records[0])
        rec_id = insert_record(record, db_path=self.db_path)
        record_duplicate(batch, rec_id, 'source_id', db_path=self.db_path)
        conn = get_connection(self.db_path)
        try:
            with conn:
                conn.execute('ALTER TABLE duplicate_audit DROP COLUMN is_synthetic')
        finally:
            conn.close()
        init_db(self.db_path)
        init_db(self.db_path)
        clean = get_database_summary(db_path=self.db_path)
        self.assertEqual(clean['total_duplicates_logged'], 0)
        self.assertIsNone(clean['latest_batch'])
        self.assertIsNone(clean['latest_collection_timestamp'])
        self.assertEqual(get_database_summary(include_synthetic=True, db_path=self.db_path)['total_duplicates_logged'], 1)

    def setUp(self):
        """Create a temporary SQLite database for each test to ensure complete isolation."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_trust.db"
        init_db(self.db_path)

        # Load synthetic fixture for testing
        fixture_path = Path(__file__).parent / "fixtures" / "synthetic_records.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            self.synthetic_records = json.load(f)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schema_creation_and_indexes(self):
        """Verify that all required tables and indexes are created properly."""
        conn = get_connection(self.db_path)
        try:
            # Check tables
            tables = [
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table';"
                ).fetchall()
            ]
            self.assertIn("records", tables)
            self.assertIn("import_batches", tables)
            self.assertIn("duplicate_audit", tables)
            self.assertIn("collection_logs", tables)

            # Check indexes on records
            indexes = [
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index';"
                ).fetchall()
            ]
            self.assertIn("idx_records_published_at", indexes)
            self.assertIn("idx_records_source", indexes)
            self.assertIn("idx_records_source_type", indexes)
            self.assertIn("idx_records_content_hash", indexes)
            self.assertIn("idx_records_canonical_url", indexes)
            self.assertIn("idx_records_original_url", indexes)
            self.assertIn("idx_records_source_id", indexes)
            self.assertIn("idx_records_batch_id", indexes)
            self.assertIn("idx_records_is_synthetic", indexes)
            self.assertIn("idx_duplicate_audit_matched_id", indexes)
        finally:
            conn.close()

    def test_init_db_is_idempotent(self):
        """Calling init_db multiple times must be safe and idempotent."""
        # Insert a record
        rec = dict(self.synthetic_records[0])
        insert_record(rec, db_path=self.db_path)

        # Re-run init_db
        init_db(self.db_path)

        # Verify record still exists intact
        fetched = get_record_by_id(rec["record_id"], db_path=self.db_path)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["title"], rec["title"])

    def test_insert_record_preserves_urls_and_provenance(self):
        """Verify that original_url and canonical_url are both preserved, and provenance fields validated."""
        rec = dict(self.synthetic_records[0])
        rec_id = insert_record(rec, db_path=self.db_path)
        self.assertEqual(rec_id, rec["record_id"])

        fetched = get_record_by_id(rec_id, db_path=self.db_path)
        self.assertEqual(fetched["original_url"], rec["original_url"])
        self.assertEqual(fetched["canonical_url"], rec["canonical_url"])
        self.assertEqual(fetched["source"], "Reddit")
        self.assertEqual(fetched["source_type"], "customer_discussion")
        self.assertEqual(fetched["collection_method"], "API")
        self.assertEqual(fetched["is_synthetic"], 1)

    def test_insert_record_validation_errors(self):
        """Ensure invalid provenance or empty text triggers immediate validation error."""
        # Invalid source
        with self.assertRaises(ValueError):
            insert_record(
                {
                    "source": "InvalidPlatform",
                    "source_type": "customer_discussion",
                    "collection_method": "API",
                    "text": "Some comment",
                },
                db_path=self.db_path,
            )

        # Invalid source_type
        with self.assertRaises(ValueError):
            insert_record(
                {
                    "source": "News",
                    "source_type": "invalid_type",
                    "collection_method": "GDELT",
                    "text": "News article body",
                },
                db_path=self.db_path,
            )

        # Empty text
        with self.assertRaises(ValueError):
            insert_record(
                {
                    "source": "Reddit",
                    "source_type": "customer_discussion",
                    "collection_method": "API",
                    "text": "   ",
                },
                db_path=self.db_path,
            )

    def test_batch_lifecycle_and_logging(self):
        """Test creating, updating, and logging within an import batch."""
        batch_id = start_batch(
            source="News",
            collection_method="GDELT",
            batch_name="Test GDELT Run",
            is_synthetic=True,
            db_path=self.db_path,
        )
        self.assertTrue(batch_id.startswith("batch_"))

        log_event(batch_id, "INFO", "Started fetching articles", db_path=self.db_path)

        finish_batch(
            batch_id=batch_id,
            status="completed",
            processed=10,
            imported=8,
            duplicate=2,
            invalid=0,
            db_path=self.db_path,
        )

        conn = get_connection(self.db_path)
        try:
            batch = conn.execute(
                "SELECT * FROM import_batches WHERE batch_id = ?;", (batch_id,)
            ).fetchone()
            self.assertEqual(batch["status"], "completed")
            self.assertEqual(batch["records_imported"], 8)
            self.assertEqual(batch["records_duplicate"], 2)

            log_entry = conn.execute(
                "SELECT * FROM collection_logs WHERE batch_id = ?;", (batch_id,)
            ).fetchone()
            self.assertEqual(log_entry["level"], "INFO")
            self.assertIn("Started fetching articles", log_entry["message"])
        finally:
            conn.close()

    def test_find_existing_record_three_tiers(self):
        """Test the 3-tier deduplication sequence: source_id -> canonical_url -> content_hash."""
        rec = dict(self.synthetic_records[0])
        rec_id = insert_record(rec, db_path=self.db_path)

        # Tier 1: Match source_id within the same source
        matched_id, reason = find_existing_record(
            source=rec["source"],
            source_type=rec["source_type"],
            source_id=rec["source_id"],
            canonical_url="https://different-url.com",
            content_hash="different_hash",
            db_path=self.db_path,
        )
        self.assertEqual(matched_id, rec_id)
        self.assertEqual(reason, "source_id")

        # Tier 2: Match canonical_url
        matched_id, reason = find_existing_record(
            source="Imported",
            source_type="customer_discussion",
            source_id=None,
            canonical_url=rec["canonical_url"],
            content_hash="different_hash",
            db_path=self.db_path,
        )
        self.assertEqual(matched_id, rec_id)
        self.assertEqual(reason, "canonical_url")

        # Tier 3: Match content_hash within compatible platform provenance (same source and source_type)
        matched_id, reason = find_existing_record(
            source=rec["source"],  # Reddit
            source_type=rec["source_type"],  # customer_discussion
            source_id=None,
            canonical_url=None,
            content_hash=rec["content_hash"],
            db_path=self.db_path,
        )
        self.assertEqual(matched_id, rec_id)
        self.assertEqual(reason, "content_hash")

        # Tier 3 Platform Provenance Isolation: Same text from a DIFFERENT platform (Imported vs Reddit) must NOT match
        matched_id, reason = find_existing_record(
            source="Imported",
            source_type=rec["source_type"],  # customer_discussion
            source_id=None,
            canonical_url=None,
            content_hash=rec["content_hash"],
            db_path=self.db_path,
        )
        self.assertIsNone(matched_id)
        self.assertIsNone(reason)

        # Tier 3 Source Type Isolation: Same content_hash in a DIFFERENT source_type must NOT match
        matched_id, reason = find_existing_record(
            source="News",
            source_type="media",  # different source_type
            source_id=None,
            canonical_url=None,
            content_hash=rec["content_hash"],
            db_path=self.db_path,
        )
        self.assertIsNone(matched_id)
        self.assertIsNone(reason)

    def test_duplicate_audit_tracking(self):
        """Ensure duplicate attempts are recorded in duplicate_audit and not in records table."""
        batch_id = start_batch("Imported", "CSV import", db_path=self.db_path)
        rec = dict(self.synthetic_records[0])
        rec_id = insert_record(rec, db_path=self.db_path)

        # Record a duplicate attempt referencing the valid batch
        record_duplicate(
            batch_id=batch_id,
            matched_record_id=rec_id,
            match_reason="content_hash",
            duplicate_source="Imported",
            duplicate_source_type="customer_discussion",
            duplicate_content_hash=rec["content_hash"],
            db_path=self.db_path,
        )

        conn = get_connection(self.db_path)
        try:
            # Check duplicate_audit table
            dup = conn.execute(
                "SELECT * FROM duplicate_audit WHERE matched_record_id = ?;", (rec_id,)
            ).fetchone()
            self.assertIsNotNone(dup)
            self.assertEqual(dup["match_reason"], "content_hash")
            self.assertEqual(dup["duplicate_source"], "Imported")
            self.assertEqual(dup["batch_id"], batch_id)

            # Canonical records table must still have exactly 1 record
            count = conn.execute("SELECT COUNT(*) as cnt FROM records;").fetchone()["cnt"]
            self.assertEqual(count, 1)
        finally:
            conn.close()

    def test_atomic_transaction_success(self):
        """Test atomic multi-record insertion with duplicates in a single transaction."""
        batch_id = start_batch("Imported", "CSV import", db_path=self.db_path)

        # First insert 1 record
        rec1 = dict(self.synthetic_records[0])
        insert_record(rec1, db_path=self.db_path)

        # Batch insert: 1 new record + 1 duplicate attempt
        rec2 = dict(self.synthetic_records[1])
        duplicates = [
            {
                "matched_record_id": rec1["record_id"],
                "match_reason": "canonical_url",
                "source": "Imported",
                "source_type": "customer_discussion",
                "canonical_url": rec1["canonical_url"],
            }
        ]

        result = insert_records_atomic(
            records=[rec2],
            duplicates=duplicates,
            batch_id=batch_id,
            db_path=self.db_path,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["imported_count"], 1)
        self.assertEqual(result["duplicate_count"], 1)

        # Verify batch summary updated
        conn = get_connection(self.db_path)
        try:
            batch = conn.execute(
                "SELECT * FROM import_batches WHERE batch_id = ?;", (batch_id,)
            ).fetchone()
            self.assertEqual(batch["records_imported"], 1)
            self.assertEqual(batch["records_duplicate"], 1)
            self.assertEqual(batch["records_processed"], 2)
        finally:
            conn.close()

    def test_atomic_transaction_rollback_on_failure(self):
        """If one record in a batch fails, the entire transaction must roll back."""
        batch_id = start_batch("Imported", "CSV import", db_path=self.db_path)

        rec1 = dict(self.synthetic_records[0])
        # rec2 has an invalid source which violates constraints
        rec2_invalid = {
            "record_id": "rec_invalid_999",
            "source": "NON_EXISTENT_SOURCE",
            "source_type": "media",
            "collection_method": "API",
            "text": "Valid text body",
        }

        with self.assertRaises(ValueError):
            insert_records_atomic(
                records=[rec1, rec2_invalid],
                batch_id=batch_id,
                db_path=self.db_path,
            )

        # Verify that rec1 was NOT inserted due to rollback
        conn = get_connection(self.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) as cnt FROM records;").fetchone()["cnt"]
            self.assertEqual(count, 0)
        finally:
            conn.close()

    def test_synthetic_data_isolation(self):
        """Synthetic records must be excluded from research summary counts by default."""
        # Insert 1 synthetic customer discussion and 1 synthetic media record
        for rec in self.synthetic_records:
            insert_record(rec, db_path=self.db_path)

        # Summary without synthetic data
        summary_clean = get_database_summary(include_synthetic=False, db_path=self.db_path)
        self.assertEqual(summary_clean["total_records"], 0)
        self.assertEqual(summary_clean["customer_discussions"], 0)
        self.assertEqual(summary_clean["media_records"], 0)

        # Summary with synthetic data explicitly included
        summary_all = get_database_summary(include_synthetic=True, db_path=self.db_path)
        self.assertEqual(summary_all["total_records"], 2)
        self.assertEqual(summary_all["customer_discussions"], 1)
        self.assertEqual(summary_all["media_records"], 1)


    def test_foreign_key_constraints_enforced(self):
        """Verify that SQLite foreign key constraints are strictly enforced."""
        # Inserting a duplicate pointing to a non-existent matched_record_id must fail
        with self.assertRaises(sqlite3.IntegrityError):
            record_duplicate(
                batch_id=None,
                matched_record_id="non_existent_rec_id",
                match_reason="canonical_url",
                db_path=self.db_path,
            )

        # Inserting a record pointing to a non-existent import_batch_id must fail
        rec = dict(self.synthetic_records[0])
        rec["record_id"] = "rec_fk_test"
        rec["import_batch_id"] = "non_existent_batch_id"
        with self.assertRaises(sqlite3.IntegrityError):
            insert_record(rec, db_path=self.db_path)


    def test_relevance_flag_field(self):
        """relevance_flag column is present, defaults to NULL, and stores allowed values."""
        conn = get_connection(self.db_path)
        try:
            # Verify column exists via PRAGMA
            columns = {row[1] for row in conn.execute("PRAGMA table_info(records);").fetchall()}
            self.assertIn("relevance_flag", columns)
            # Verify index exists
            indexes = [
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index';"
                ).fetchall()
            ]
            self.assertIn("idx_records_relevance_flag", indexes)
        finally:
            conn.close()

        # Insert record without relevance_flag → should default to NULL
        rec = dict(self.synthetic_records[0])
        rec_id = insert_record(rec, db_path=self.db_path)
        fetched = get_record_by_id(rec_id, db_path=self.db_path)
        self.assertIsNone(fetched["relevance_flag"])

        # Insert a second record with an explicit relevance_flag
        rec2 = dict(self.synthetic_records[1])
        rec2["relevance_flag"] = "contextual"
        rec2_id = insert_record(rec2, db_path=self.db_path)
        fetched2 = get_record_by_id(rec2_id, db_path=self.db_path)
        self.assertEqual(fetched2["relevance_flag"], "contextual")

    def test_init_db_migration_adds_relevance_flag_to_existing_db(self):
        """init_db safely adds relevance_flag column to a pre-existing database."""
        import sqlite3 as _sqlite3

        # Create a legacy-style DB without the relevance_flag column
        legacy_dir = tempfile.TemporaryDirectory()
        legacy_path = Path(legacy_dir.name) / "legacy.db"
        try:
            conn = _sqlite3.connect(str(legacy_path))
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    record_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT,
                    title TEXT,
                    text TEXT NOT NULL,
                    normalized_text TEXT NOT NULL,
                    original_url TEXT,
                    canonical_url TEXT,
                    published_at TEXT,
                    collected_at TEXT NOT NULL,
                    domain TEXT,
                    collection_method TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    import_batch_id TEXT,
                    status TEXT NOT NULL DEFAULT 'valid',
                    is_synthetic INTEGER NOT NULL DEFAULT 0,
                    raw_payload TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS import_batches (
                    batch_id TEXT PRIMARY KEY,
                    batch_name TEXT,
                    source TEXT NOT NULL,
                    collection_method TEXT NOT NULL,
                    status TEXT NOT NULL,
                    records_processed INTEGER DEFAULT 0,
                    records_imported INTEGER DEFAULT 0,
                    records_duplicate INTEGER DEFAULT 0,
                    records_invalid INTEGER DEFAULT 0,
                    error_details TEXT,
                    is_synthetic INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS duplicate_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT,
                    duplicate_source TEXT,
                    duplicate_source_type TEXT,
                    duplicate_source_id TEXT,
                    duplicate_original_url TEXT,
                    duplicate_content_hash TEXT,
                    matched_record_id TEXT NOT NULL,
                    match_reason TEXT NOT NULL,
                    attempted_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS collection_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
            conn.close()

            # Verify column is absent before migration
            conn2 = _sqlite3.connect(str(legacy_path))
            cols_before = {row[1] for row in conn2.execute("PRAGMA table_info(records);").fetchall()}
            self.assertNotIn("relevance_flag", cols_before)
            conn2.close()

            # Run init_db — should add the column idempotently
            init_db(legacy_path)

            conn3 = _sqlite3.connect(str(legacy_path))
            cols_after = {row[1] for row in conn3.execute("PRAGMA table_info(records);").fetchall()}
            self.assertIn("relevance_flag", cols_after)
            conn3.close()

            # Calling init_db a second time must not raise
            init_db(legacy_path)
        finally:
            legacy_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
