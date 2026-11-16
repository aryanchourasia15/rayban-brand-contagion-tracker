"""
Ray-Ban Customer Trust Intelligence
3-Tier Deduplication Engine and Concurrency-Safe Batch Ingestion
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.data.cleaner import (
    canonicalize_url,
    compute_content_hash,
    is_generic_or_too_short,
    normalize_text,
    parse_date_to_utc_iso,
)
from src.data.db import (
    find_existing_record,
    get_connection,
    insert_records_atomic,
    log_event,
    record_duplicate,
)


class DeduplicationEngine:
    """
    3-Tier Deduplication Engine enforcing:
    1. Platform source ID within the same source.
    2. Canonical URL across records.
    3. Exact normalized-text SHA-256 hash within compatible platform provenance
       (same source and same source_type), safeguarded against false positives on
       short/generic comments.
    """

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = db_path

    def process_and_deduplicate_record(
        self,
        record: Dict[str, Any],
        conn=None,
    ) -> Tuple[bool, Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        Clean, normalize, and check a single record against the database.

        Returns:
            (is_duplicate, processed_record, duplicate_audit_dict_or_none)
        """
        source = record.get("source", "Imported")
        source_type = record.get("source_type", "customer_discussion")
        source_id = record.get("source_id")

        # Ensure clean text & hash
        raw_text = record.get("text", "")
        normalized_text = normalize_text(raw_text)
        content_hash = compute_content_hash(normalized_text)

        # Canonicalize URLs
        orig_url = record.get("original_url") or record.get("url")
        canonical_url, domain = canonicalize_url(orig_url)

        # Parse date respecting source-specific documented rules
        published_at = parse_date_to_utc_iso(record.get("published_at"), source=source)

        # Build clean candidate record
        cleaned_rec = dict(record)
        cleaned_rec["source"] = source
        cleaned_rec["source_type"] = source_type
        cleaned_rec["text"] = str(raw_text)
        cleaned_rec["normalized_text"] = normalized_text
        cleaned_rec["content_hash"] = content_hash
        cleaned_rec["original_url"] = orig_url
        cleaned_rec["canonical_url"] = canonical_url
        cleaned_rec["domain"] = domain or record.get("domain")
        cleaned_rec["published_at"] = published_at

        # Populate heuristic relevance_flag if not already set
        if not cleaned_rec.get("relevance_flag"):
            from src.data.classifier import classify_relevance
            cleaned_rec["relevance_flag"] = classify_relevance(
                text=raw_text, title=record.get("title"), url=orig_url
            )

        # Guard against false positives on Tier 3 (generic or short phrases)
        hash_to_query = (
            None if is_generic_or_too_short(normalized_text) else content_hash
        )

        matched_id, match_reason = find_existing_record(
            source=source,
            source_type=source_type,
            source_id=source_id,
            canonical_url=canonical_url,
            content_hash=hash_to_query,
            conn=conn,
            db_path=self.db_path,
        )

        if matched_id:
            duplicate_info = {
                "matched_record_id": matched_id,
                "match_reason": match_reason,
                "source": source,
                "source_type": source_type,
                "source_id": source_id,
                "original_url": orig_url,
                "content_hash": content_hash,
                "is_synthetic": cleaned_rec.get("is_synthetic", 0),
            }
            return True, cleaned_rec, duplicate_info

        return False, cleaned_rec, None

    def deduplicate_batch(
        self,
        raw_records: List[Dict[str, Any]],
        batch_id: Optional[str] = None,
        conn: Optional[Any] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Process a list of candidate records against the database AND in-memory
        against previously accepted records within the current batch.

        Returns:
            (valid_records_to_insert, duplicate_audit_entries)
        """
        valid_records: List[Dict[str, Any]] = []
        duplicate_entries: List[Dict[str, Any]] = []

        # In-memory tracking for in-batch deduplication
        seen_source_ids: Dict[Tuple[str, str], str] = {}
        seen_canonical_urls: Dict[str, str] = {}
        # Restricted to compatible platform provenance: (source, source_type, content_hash) -> list of (rec_id, canonical_url)
        seen_content_hashes: Dict[Tuple[str, str, str], List[Tuple[str, Optional[str]]]] = {}

        close_after = False
        if conn is None:
            conn = get_connection(self.db_path)
            close_after = True

        try:
            for raw_rec in raw_records:
                # 1. Check against DB
                is_dup, cleaned_rec, dup_info = self.process_and_deduplicate_record(
                    raw_rec, conn=conn
                )

                if is_dup and dup_info:
                    dup_info["batch_id"] = batch_id
                    duplicate_entries.append(dup_info)
                    continue

                # 2. Check against in-batch seen records
                source = cleaned_rec.get("source", "Imported")
                source_type = cleaned_rec.get("source_type", "customer_discussion")
                source_id = cleaned_rec.get("source_id")
                canonical_url = cleaned_rec.get("canonical_url")
                content_hash = cleaned_rec["content_hash"]
                norm_text = cleaned_rec["normalized_text"]

                in_batch_matched_id = None
                in_batch_reason = None

                # Tier 1 in-batch: platform source_id within same platform
                if source_id and (source, source_id) in seen_source_ids:
                    in_batch_matched_id = seen_source_ids[(source, source_id)]
                    in_batch_reason = "source_id"

                # Tier 2 in-batch: canonical_url
                elif canonical_url and canonical_url in seen_canonical_urls:
                    in_batch_matched_id = seen_canonical_urls[canonical_url]
                    in_batch_reason = "canonical_url"

                # Tier 3 in-batch: exact content hash within same (source, source_type)
                elif (
                    not is_generic_or_too_short(norm_text)
                    and (source, source_type, content_hash) in seen_content_hashes
                ):
                    candidates_seen = seen_content_hashes[(source, source_type, content_hash)]
                    matched_id = None
                    for seen_rec_id, seen_canon_url in candidates_seen:
                        # Disable text-hash deduplication for URL-bearing news articles when canonical URLs differ
                        if (source == "News" or source_type == "media") and (canonical_url or seen_canon_url):
                            incoming_canon = canonical_url.strip() if canonical_url else None
                            exist_canon = seen_canon_url.strip() if seen_canon_url else None
                            if incoming_canon != exist_canon:
                                continue
                        matched_id = seen_rec_id
                        break

                    if matched_id:
                        in_batch_matched_id = matched_id
                        in_batch_reason = "content_hash"

                if in_batch_matched_id:
                    dup_entry = {
                        "batch_id": batch_id,
                        "matched_record_id": in_batch_matched_id,
                        "match_reason": in_batch_reason,
                        "source": source,
                        "source_type": source_type,
                        "source_id": source_id,
                        "original_url": cleaned_rec.get("original_url"),
                        "content_hash": content_hash,
                        "is_synthetic": cleaned_rec.get("is_synthetic", 0),
                    }
                    duplicate_entries.append(dup_entry)
                    continue

                # Record is unique: assign an ID if not present and register in-batch
                rec_id = cleaned_rec.get("record_id")
                if not rec_id:
                    import uuid
                    rec_id = f"rec_{uuid.uuid4().hex[:14]}"
                    cleaned_rec["record_id"] = rec_id

                if batch_id:
                    cleaned_rec["import_batch_id"] = batch_id

                # Register in-memory for subsequent items in the batch
                if source_id:
                    seen_source_ids[(source, source_id)] = rec_id
                if canonical_url:
                    seen_canonical_urls[canonical_url] = rec_id
                if not is_generic_or_too_short(norm_text):
                    hash_key = (source, source_type, content_hash)
                    if hash_key not in seen_content_hashes:
                        seen_content_hashes[hash_key] = []
                    seen_content_hashes[hash_key].append((rec_id, canonical_url))

                valid_records.append(cleaned_rec)

        finally:
            if close_after:
                conn.close()

        return valid_records, duplicate_entries

    def ingest_batch_safely(
        self,
        raw_records: List[Dict[str, Any]],
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Concurrency-safe end-to-end ingestion:
        - Acquires SQLite write lock (BEGIN IMMEDIATE)
        - Runs deduplication (DB and in-batch) within the write transaction
        - Inserts valid records and duplicate audit entries atomically
        - Commits on success, rolls back on error
        """
        conn = get_connection(self.db_path)
        conn.isolation_level = None
        try:
            conn.execute("BEGIN IMMEDIATE;")

            valid_records, duplicate_entries = self.deduplicate_batch(
                raw_records, batch_id=batch_id, conn=conn
            )

            res = insert_records_atomic(
                records=valid_records,
                duplicates=duplicate_entries,
                batch_id=batch_id,
                conn=conn,
                db_path=self.db_path,
            )

            conn.execute("COMMIT;")

            return {
                "batch_id": batch_id,
                "processed": len(raw_records),
                "imported": len(valid_records),
                "duplicate": len(duplicate_entries),
                "imported_ids": res.get("imported_ids", []),
            }
        except Exception as e:
            conn.execute("ROLLBACK;")
            if batch_id:
                try:
                    log_event(
                        batch_id,
                        "ERROR",
                        f"Batch ingestion failed: {str(e)}",
                        db_path=self.db_path,
                    )
                except Exception:
                    pass
            raise e
        finally:
            conn.close()
