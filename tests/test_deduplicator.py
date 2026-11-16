"""
Unit tests for Module 2: DeduplicationEngine (3-Tier deduplication, generic guards, batch & idempotency).
"""

import json
import tempfile
import unittest
from pathlib import Path

from src.data.db import (
    get_connection,
    get_database_summary,
    get_duplicate_audits,
    init_db,
    start_batch,
)
from src.data.deduplicator import DeduplicationEngine


class TestDeduplicatorModule(unittest.TestCase):
    def setUp(self):
        """Create an isolated temporary SQLite database for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_dedup.db"
        init_db(self.db_path)
        self.engine = DeduplicationEngine(db_path=self.db_path)

        # Load synthetic fixture
        fixture_path = Path(__file__).parent / "fixtures" / "synthetic_records.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            self.synthetic_records = json.load(f)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_tier1_source_id_matching(self):
        """Tier 1: Matches on source_id within the same source platform."""
        batch_id = start_batch("Reddit", "API", db_path=self.db_path)
        rec = dict(self.synthetic_records[0])  # Reddit source_id: reddit_post_abc123

        # First ingestion
        res1 = self.engine.ingest_batch_safely([rec], batch_id=batch_id)
        self.assertEqual(res1["imported"], 1)
        self.assertEqual(res1["duplicate"], 0)

        # Candidate with same source_id and source, but different URL and text
        candidate = {
            "source": "Reddit",
            "source_type": "customer_discussion",
            "source_id": "reddit_post_abc123",
            "text": "Completely revised post text about camera concerns",
            "url": "https://reddit.com/r/privacy/comments/different_url",
            "collection_method": "API",
        }

        is_dup, cleaned, dup_info = self.engine.process_and_deduplicate_record(candidate)
        self.assertTrue(is_dup)
        self.assertEqual(dup_info["match_reason"], "source_id")
        self.assertEqual(dup_info["matched_record_id"], rec["record_id"])

    def test_tier2_canonical_url_matching(self):
        """Tier 2: Matches on canonical_url across sources."""
        batch_id = start_batch("News", "GDELT", db_path=self.db_path)
        rec = dict(self.synthetic_records[1])  # TheVerge canonical URL

        self.engine.ingest_batch_safely([rec], batch_id=batch_id)

        # Candidate with different source and text, but identical canonical URL (with extra tracking params)
        candidate = {
            "source": "Imported",
            "source_type": "media",
            "source_id": "different_source_id",
            "text": "Syndicated reprint of European privacy scrutiny article",
            "url": "https://theverge.com/2024/2/1/smart-glasses-privacy-europe?utm_source=newsletter&utm_medium=email",
            "collection_method": "CSV import",
        }

        is_dup, cleaned, dup_info = self.engine.process_and_deduplicate_record(candidate)
        self.assertTrue(is_dup)
        self.assertEqual(dup_info["match_reason"], "canonical_url")
        self.assertEqual(dup_info["matched_record_id"], rec["record_id"])

    def test_tier3_content_hash_matching_same_platform_provenance(self):
        """Tier 3: Matches on exact content hash within compatible platform provenance (same source and source_type)."""
        batch_id = start_batch("Reddit", "API", db_path=self.db_path)
        rec = dict(self.synthetic_records[0])  # source: Reddit, source_type: customer_discussion

        self.engine.ingest_batch_safely([rec], batch_id=batch_id)

        # Candidate from the SAME platform (Reddit) with no source_id and different URL, but identical substantial text
        candidate = {
            "source": "Reddit",  # compatible platform provenance
            "source_type": "customer_discussion",
            "source_id": None,
            "text": rec["text"].upper(),  # different casing, but normalizes identically
            "url": "https://reddit.com/r/technology/comments/repost-gym",
            "collection_method": "API",
        }

        is_dup, cleaned, dup_info = self.engine.process_and_deduplicate_record(candidate)
        self.assertTrue(is_dup)
        self.assertEqual(dup_info["match_reason"], "content_hash")
        self.assertEqual(dup_info["matched_record_id"], rec["record_id"])

    def test_tier3_platform_provenance_isolation(self):
        """Distinct customer comments from different platforms must remain separate, even with identical text."""
        batch_id = start_batch("Reddit", "API", db_path=self.db_path)
        rec = dict(self.synthetic_records[0])  # source: Reddit, source_type: customer_discussion

        self.engine.ingest_batch_safely([rec], batch_id=batch_id)

        # Candidate with identical text from a DIFFERENT platform (Imported)
        candidate = {
            "source": "Imported",  # different platform provenance
            "source_type": "customer_discussion",
            "source_id": None,
            "text": rec["text"],
            "url": "https://forums.macrumors.com/threads/repost-gym",
            "collection_method": "CSV import",
        }

        is_dup, cleaned, dup_info = self.engine.process_and_deduplicate_record(candidate)
        # Must NOT be deduplicated across different platforms
        self.assertFalse(is_dup)
        self.assertIsNone(dup_info)

    def test_tier3_isolation_across_different_source_types(self):
        """Tier 3 does NOT match across different source types (media vs customer discussion)."""
        batch_id = start_batch("Reddit", "API", db_path=self.db_path)
        rec = dict(self.synthetic_records[0])  # customer_discussion

        self.engine.ingest_batch_safely([rec], batch_id=batch_id)

        # Candidate has identical text but is a media article
        candidate = {
            "source": "News",
            "source_type": "media",  # different source_type
            "source_id": None,
            "text": rec["text"],
            "url": "https://techtimes.com/news-quote",
            "collection_method": "GDELT",
        }

        is_dup, cleaned, dup_info = self.engine.process_and_deduplicate_record(candidate)
        self.assertFalse(is_dup)
        self.assertIsNone(dup_info)

    def test_generic_and_short_comments_avoid_false_positives(self):
        """Generic or short comments should not be deduplicated on content hash."""
        batch_id = start_batch("Reddit", "API", db_path=self.db_path)

        rec1 = {
            "record_id": "rec_short_1",
            "source": "Reddit",
            "source_type": "customer_discussion",
            "source_id": "post_short_1",
            "text": "I agree completely with this statement.",
            "url": "https://reddit.com/r/rayban/1",
            "collection_method": "API",
        }
        self.engine.ingest_batch_safely([rec1], batch_id=batch_id)

        # Distinct user posting the same short generic sentence
        rec2 = {
            "record_id": "rec_short_2",
            "source": "Reddit",
            "source_type": "customer_discussion",
            "source_id": "post_short_2",  # distinct post ID
            "text": "I agree completely with this statement.",  # identical short generic text
            "url": "https://reddit.com/r/rayban/2",  # distinct URL
            "collection_method": "API",
        }

        is_dup, cleaned, dup_info = self.engine.process_and_deduplicate_record(rec2)
        # Should NOT be flagged as duplicate
        self.assertFalse(is_dup)
        self.assertIsNone(dup_info)

    def test_in_batch_deduplication(self):
        """In-batch deduplication catches duplicates within the same uploaded list/file."""
        batch_id = start_batch("Imported", "CSV import", db_path=self.db_path)

        rec_a = {
            "record_id": "rec_batch_001",
            "source": "Imported",
            "source_type": "customer_discussion",
            "source_id": "row_101",
            "text": "The privacy light on the front is too dim to alert bystanders in daylight.",
            "url": "https://reddit.com/r/technology/comments/light",
            "collection_method": "CSV import",
        }

        # Second row in same batch has identical canonical URL and identical text
        rec_b = {
            "record_id": "rec_batch_002",
            "source": "Imported",
            "source_type": "customer_discussion",
            "source_id": "row_102",
            "text": "The privacy light on the front is too dim to alert bystanders in daylight.",
            "url": "https://reddit.com/r/technology/comments/light?utm_source=twitter",
            "collection_method": "CSV import",
        }

        res = self.engine.ingest_batch_safely([rec_a, rec_b], batch_id=batch_id)
        self.assertEqual(res["imported"], 1)
        self.assertEqual(res["duplicate"], 1)

        # Verify database has only 1 canonical record
        conn = get_connection(self.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) as cnt FROM records;").fetchone()["cnt"]
            self.assertEqual(count, 1)

            # Duplicate audit has 1 entry
            dup_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM duplicate_audit;"
            ).fetchone()["cnt"]
            self.assertEqual(dup_count, 1)
        finally:
            conn.close()

    def test_repeated_imports_idempotency(self):
        """Uploading the exact same records twice must be completely idempotent."""
        batch_id_1 = start_batch("Imported", "CSV import", db_path=self.db_path)
        records = [dict(r) for r in self.synthetic_records]

        # 1st run: all records imported
        res1 = self.engine.ingest_batch_safely(records, batch_id=batch_id_1)
        self.assertEqual(res1["imported"], len(records))
        self.assertEqual(res1["duplicate"], 0)

        # 2nd run with new batch: 0 imported, all detected as duplicates
        batch_id_2 = start_batch("Imported", "CSV import", db_path=self.db_path)
        res2 = self.engine.ingest_batch_safely(records, batch_id=batch_id_2)
        self.assertEqual(res2["imported"], 0)
        self.assertEqual(res2["duplicate"], len(records))

        # Check total canonical records in DB remains len(records)
        summary = get_database_summary(include_synthetic=True, db_path=self.db_path)
        self.assertEqual(summary["total_records"], len(records))
        self.assertEqual(summary["total_duplicates_logged"], len(records))

        # Check duplicate audits contain correct matched_record_ids
        audits = get_duplicate_audits(batch_id=batch_id_2, db_path=self.db_path)
        self.assertEqual(len(audits), len(records))
        matched_ids = {a["matched_record_id"] for a in audits}
        original_ids = {r["record_id"] for r in records}
        self.assertEqual(matched_ids, original_ids)

    def test_concurrency_safe_write_transaction(self):
        """
        Regression test: Multiple threads concurrently ingesting identical records
        must not create duplicate canonical records or race conditions.
        """
        import concurrent.futures

        records_to_ingest = [dict(r) for r in self.synthetic_records]
        num_workers = 4

        def worker_task(worker_idx):
            engine = DeduplicationEngine(db_path=self.db_path)
            batch_id = start_batch("Reddit", "API", batch_name=f"worker_{worker_idx}", db_path=self.db_path)
            return engine.ingest_batch_safely(records_to_ingest, batch_id=batch_id)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker_task, i) for i in range(num_workers)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        total_imported = sum(r["imported"] for r in results)
        total_duplicates = sum(r["duplicate"] for r in results)

        # Exactly 2 canonical records must be imported across all threads
        self.assertEqual(total_imported, len(self.synthetic_records))
        # The remaining 3 threads (x2 records = 6) must be detected as duplicates
        self.assertEqual(total_duplicates, (num_workers - 1) * len(self.synthetic_records))

        # Direct database verification
        conn = get_connection(self.db_path)
        try:
            canonical_count = conn.execute("SELECT COUNT(*) as cnt FROM records;").fetchone()["cnt"]
            self.assertEqual(canonical_count, len(self.synthetic_records))

            dup_count = conn.execute("SELECT COUNT(*) as cnt FROM duplicate_audit;").fetchone()["cnt"]
            self.assertEqual(dup_count, (num_workers - 1) * len(self.synthetic_records))
        finally:
            conn.close()

    def test_news_articles_with_different_urls_not_merged_on_identical_headlines(self):
        """
        Regression test: News articles with different canonical URLs must NOT be
        merged solely because they share identical headlines.
        Text-hash deduplication is disabled for URL-bearing news articles when canonical URLs differ,
        while preserving exact URL match deduplication.
        """
        batch_id = start_batch("News", "GDELT", db_path=self.db_path)
        headline = "Ray-Ban Meta smart glasses spark new European privacy investigation"

        article_reuters = {
            "source": "News",
            "source_type": "media",
            "source_id": "https://www.reuters.com/technology/ray-ban-meta-privacy-inquiry",
            "title": headline,
            "text": headline,
            "url": "https://www.reuters.com/technology/ray-ban-meta-privacy-inquiry",
            "collection_method": "GDELT",
        }
        article_ap = {
            "source": "News",
            "source_type": "media",
            "source_id": "https://apnews.com/article/meta-rayban-glasses-privacy-probe",
            "title": headline,
            "text": headline,
            "url": "https://apnews.com/article/meta-rayban-glasses-privacy-probe",
            "collection_method": "GDELT",
        }
        # Exact duplicate of the Reuters article (different tracking params, same canonical URL)
        article_reuters_dup = {
            "source": "News",
            "source_type": "media",
            "source_id": "https://www.reuters.com/technology/ray-ban-meta-privacy-inquiry",
            "title": headline,
            "text": headline,
            "url": "https://www.reuters.com/technology/ray-ban-meta-privacy-inquiry?utm_source=twitter",
            "collection_method": "GDELT",
        }

        # Ingest both distinct publisher articles in the same batch
        res = self.engine.ingest_batch_safely([article_reuters, article_ap, article_reuters_dup], batch_id=batch_id)
        # Both distinct articles should be imported; only the exact URL duplicate should be rejected
        self.assertEqual(res["imported"], 2)
        self.assertEqual(res["duplicate"], 1)

        # Confirm in SQLite: both records exist with distinct canonical URLs
        conn = get_connection(self.db_path)
        try:
            records = conn.execute("SELECT record_id, canonical_url, text FROM records WHERE source = 'News';").fetchall()
            self.assertEqual(len(records), 2)
            urls = {r["canonical_url"] for r in records}
            self.assertIn("https://reuters.com/technology/ray-ban-meta-privacy-inquiry", urls)
            self.assertIn("https://apnews.com/article/meta-rayban-glasses-privacy-probe", urls)
        finally:
            conn.close()

        # Ingest in a subsequent batch: AP news article again (should be caught by Tier 2 canonical_url)
        batch_id_2 = start_batch("News", "GDELT", db_path=self.db_path)
        res2 = self.engine.ingest_batch_safely([article_ap], batch_id=batch_id_2)
        self.assertEqual(res2["imported"], 0)
        self.assertEqual(res2["duplicate"], 1)


if __name__ == "__main__":
    unittest.main()
