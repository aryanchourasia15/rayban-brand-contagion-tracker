"""
Ray-Ban Customer Trust Intelligence
Database Management, Schema Migrations, and Transaction Operations
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.config import (
    DB_PATH,
    MATCH_REASONS,
    VALID_BATCH_STATUSES,
    VALID_COLLECTION_METHODS,
    VALID_RECORD_STATUSES,
    VALID_SOURCE_TYPES,
    VALID_SOURCES,
)


def get_utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def get_connection(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """
    Establish and configure a SQLite database connection with WAL mode
    and enforced foreign key constraints.
    """
    target_path = Path(db_path) if db_path else DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(target_path), timeout=30.0)
    conn.row_factory = sqlite3.Row

    # Performance and integrity pragmas
    conn.execute("PRAGMA foreign_keys = ON;")
    # In-memory databases (:memory:) do not support WAL mode
    if str(target_path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")

    return conn


def init_db(db_path: Optional[Union[str, Path]] = None) -> None:
    """
    Initialize SQLite database tables and indexes if they do not exist.
    Safely applies non-destructive migrations.
    """
    conn = get_connection(db_path)
    try:
        with conn:
            # 1. Main Canonical Records Table
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
                    relevance_flag TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(import_batch_id) REFERENCES import_batches(batch_id) ON DELETE SET NULL
                );
                """
            )

            # 2. Ingestion Batches Table
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

            # 3. Dedicated Duplicate Audit Log
            # Tracks all duplicate attempts and identifies the canonical record they matched
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
                    is_synthetic INTEGER NOT NULL DEFAULT 0,
                    attempted_at TEXT NOT NULL,
                    FOREIGN KEY(matched_record_id) REFERENCES records(record_id) ON DELETE CASCADE,
                    FOREIGN KEY(batch_id) REFERENCES import_batches(batch_id) ON DELETE SET NULL
                );
                """
            )

            # 4. Collection & Ingestion Logs Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS collection_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(batch_id) REFERENCES import_batches(batch_id) ON DELETE SET NULL
                );
                """
            )

            # --- Non-destructive migration: add relevance_flag column if absent ---
            # SQLite does not support ALTER TABLE ... ADD COLUMN IF NOT EXISTS,
            # so we check PRAGMA table_info first.
            # This must run BEFORE index creation so the column exists when the index is built.
            existing_columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(records);").fetchall()
            }
            if "relevance_flag" not in existing_columns:
                conn.execute(
                    "ALTER TABLE records ADD COLUMN relevance_flag TEXT DEFAULT NULL;"
                )

            audit_columns = {row[1] for row in conn.execute("PRAGMA table_info(duplicate_audit);")}
            if "is_synthetic" not in audit_columns:
                conn.execute("ALTER TABLE duplicate_audit ADD COLUMN is_synthetic INTEGER NOT NULL DEFAULT 0;")

            # Create Indexes for query performance
            indexes = [
                ("idx_records_published_at", "records", "published_at"),
                ("idx_records_source", "records", "source"),
                ("idx_records_source_type", "records", "source_type"),
                ("idx_records_content_hash", "records", "content_hash"),
                ("idx_records_canonical_url", "records", "canonical_url"),
                ("idx_records_original_url", "records", "original_url"),
                ("idx_records_source_id", "records", "source_id"),
                ("idx_records_batch_id", "records", "import_batch_id"),
                ("idx_records_is_synthetic", "records", "is_synthetic"),
                ("idx_records_relevance_flag", "records", "relevance_flag"),
                ("idx_duplicate_audit_matched_id", "duplicate_audit", "matched_record_id"),
                ("idx_duplicate_audit_batch_id", "duplicate_audit", "batch_id"),
                ("idx_import_batches_started_at", "import_batches", "started_at"),
            ]
            for idx_name, table, column in indexes:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column});")

    finally:
        conn.close()


def start_batch(
    source: str,
    collection_method: str,
    batch_name: Optional[str] = None,
    is_synthetic: bool = False,
    db_path: Optional[Union[str, Path]] = None,
) -> str:
    """Create a new import batch record and return its unique batch_id."""
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source: {source}. Must be one of {VALID_SOURCES}")
    if collection_method not in VALID_COLLECTION_METHODS:
        raise ValueError(f"Invalid collection_method: {collection_method}. Must be one of {VALID_COLLECTION_METHODS}")

    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    now = get_utc_now_iso()

    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO import_batches (
                    batch_id, batch_name, source, collection_method,
                    status, is_synthetic, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    batch_id,
                    batch_name or f"{source}_{collection_method}_{now[:10]}",
                    source,
                    collection_method,
                    "started",
                    1 if is_synthetic else 0,
                    now,
                ),
            )
    finally:
        conn.close()

    return batch_id


def finish_batch(
    batch_id: str,
    status: str = "completed",
    processed: int = 0,
    imported: int = 0,
    duplicate: int = 0,
    invalid: int = 0,
    error_details: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> None:
    """Update final status and metrics for an ingestion batch."""
    if status not in VALID_BATCH_STATUSES:
        raise ValueError(f"Invalid batch status: {status}. Must be one of {VALID_BATCH_STATUSES}")

    now = get_utc_now_iso()
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                UPDATE import_batches
                SET status = ?,
                    records_processed = ?,
                    records_imported = ?,
                    records_duplicate = ?,
                    records_invalid = ?,
                    error_details = ?,
                    completed_at = ?
                WHERE batch_id = ?;
                """,
                (
                    status,
                    processed,
                    imported,
                    duplicate,
                    invalid,
                    error_details,
                    now,
                    batch_id,
                ),
            )
    finally:
        conn.close()


def log_event(
    batch_id: Optional[str],
    level: str,
    message: str,
    db_path: Optional[Union[str, Path]] = None,
) -> None:
    """Append an event message to collection_logs."""
    conn = get_connection(db_path)
    now = get_utc_now_iso()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO collection_logs (batch_id, level, message, created_at)
                VALUES (?, ?, ?, ?);
                """,
                (batch_id, level.upper(), message, now),
            )
    finally:
        conn.close()


def find_existing_record(
    source: str,
    source_type: str,
    source_id: Optional[str] = None,
    canonical_url: Optional[str] = None,
    content_hash: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Check if a record already exists using the 3-tier deduplication sequence:
    1. Match source_id where source_id is non-empty and within the same source.
    2. Match canonical_url where canonical_url is non-empty.
    3. Match content_hash within the same source_type.

    Returns:
        (matched_record_id, match_reason) if found, else (None, None).
    """
    close_after = False
    if conn is None:
        conn = get_connection(db_path)
        close_after = True

    try:
        # 1. Match source_id within same platform
        if source_id and source_id.strip():
            cur = conn.execute(
                "SELECT record_id FROM records WHERE source = ? AND source_id = ? LIMIT 1;",
                (source, source_id.strip()),
            )
            row = cur.fetchone()
            if row:
                return row["record_id"], "source_id"

        # 2. Match canonical_url
        if canonical_url and canonical_url.strip():
            cur = conn.execute(
                "SELECT record_id FROM records WHERE canonical_url = ? LIMIT 1;",
                (canonical_url.strip(),),
            )
            row = cur.fetchone()
            if row:
                return row["record_id"], "canonical_url"

        # 3. Match content_hash within compatible platform provenance (same source and source_type)
        # Distinct customer comments from different platforms remain separate, even with identical text.
        # Disable text-hash deduplication for URL-bearing news articles when their canonical URLs differ.
        if content_hash and content_hash.strip():
            cur = conn.execute(
                "SELECT record_id, canonical_url FROM records WHERE source = ? AND source_type = ? AND content_hash = ?;",
                (source, source_type, content_hash.strip()),
            )
            for row in cur.fetchall():
                existing_canonical = row["canonical_url"]
                # URL-bearing news articles with different canonical URLs must not be merged solely because of identical headlines
                if (source == "News" or source_type == "media") and (canonical_url or existing_canonical):
                    incoming_canon = canonical_url.strip() if canonical_url else None
                    exist_canon = existing_canonical.strip() if existing_canonical else None
                    if incoming_canon != exist_canon:
                        continue
                return row["record_id"], "content_hash"

        return None, None
    finally:
        if close_after:
            conn.close()


def record_duplicate(
    batch_id: Optional[str],
    matched_record_id: str,
    match_reason: str,
    duplicate_source: Optional[str] = None,
    duplicate_source_type: Optional[str] = None,
    duplicate_source_id: Optional[str] = None,
    duplicate_original_url: Optional[str] = None,
    duplicate_content_hash: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[Union[str, Path]] = None,
    is_synthetic: bool = False,
) -> None:
    """Record a duplicate attempt in the duplicate_audit table."""
    if match_reason not in MATCH_REASONS:
        raise ValueError(f"Invalid match_reason: {match_reason}. Must be in {MATCH_REASONS}")

    close_after = False
    if conn is None:
        conn = get_connection(db_path)
        close_after = True
        should_commit = True
    else:
        should_commit = False

    now = get_utc_now_iso()
    try:
        query = """
        INSERT INTO duplicate_audit (
            batch_id, duplicate_source, duplicate_source_type,
            duplicate_source_id, duplicate_original_url, duplicate_content_hash,
            matched_record_id, match_reason, attempted_at, is_synthetic
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            batch_id,
            duplicate_source,
            duplicate_source_type,
            duplicate_source_id,
            duplicate_original_url,
            duplicate_content_hash,
            matched_record_id,
            match_reason,
            now,
            1 if is_synthetic else 0,
        )
        if should_commit:
            with conn:
                conn.execute(query, params)
        else:
            conn.execute(query, params)
    finally:
        if close_after:
            conn.close()


def insert_record(
    record: Dict[str, Any],
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> str:
    """
    Validate and insert a single record into the records table.
    Generates a record_id if not present.
    """
    # Validation of required provenance fields
    source = record.get("source")
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source '{source}'. Must be one of {VALID_SOURCES}")

    source_type = record.get("source_type")
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(f"Invalid source_type '{source_type}'. Must be one of {VALID_SOURCE_TYPES}")

    required_type = {"News": "media", "Reddit": "customer_discussion"}.get(source)
    if record.get("collection_method") == "GDELT":
        required_type = "media"
    if required_type and source_type != required_type:
        raise ValueError(f"Source '{source}' requires source_type '{required_type}'.")

    collection_method = record.get("collection_method")
    if collection_method not in VALID_COLLECTION_METHODS:
        raise ValueError(f"Invalid collection_method '{collection_method}'. Must be one of {VALID_COLLECTION_METHODS}")

    text = record.get("text")
    if not text or not str(text).strip():
        raise ValueError("Record text cannot be empty.")

    normalized_text = record.get("normalized_text", text)
    content_hash = record.get("content_hash")
    if not content_hash:
        import hashlib
        content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

    record_id = record.get("record_id") or f"rec_{uuid.uuid4().hex[:14]}"
    now = get_utc_now_iso()

    raw_payload = record.get("raw_payload")
    if isinstance(raw_payload, (dict, list)):
        raw_payload = json.dumps(raw_payload, ensure_ascii=False)

    close_after = False
    if conn is None:
        conn = get_connection(db_path)
        close_after = True
        should_commit = True
    else:
        should_commit = False

    try:
        query = """
        INSERT INTO records (
            record_id, source, source_type, source_id, title,
            text, normalized_text, original_url, canonical_url,
            published_at, collected_at, domain, collection_method,
            content_hash, import_batch_id, status, is_synthetic,
            raw_payload, relevance_flag, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            record_id,
            source,
            source_type,
            record.get("source_id"),
            record.get("title"),
            str(text),
            str(normalized_text),
            record.get("original_url"),
            record.get("canonical_url"),
            record.get("published_at"),
            record.get("collected_at") or now,
            record.get("domain"),
            collection_method,
            content_hash,
            record.get("import_batch_id"),
            record.get("status", "valid"),
            1 if record.get("is_synthetic") else 0,
            raw_payload,
            record.get("relevance_flag"),
            now,
        )
        if should_commit:
            with conn:
                conn.execute(query, params)
        else:
            conn.execute(query, params)
        return record_id
    finally:
        if close_after:
            conn.close()


def insert_records_atomic(
    records: List[Dict[str, Any]],
    duplicates: Optional[List[Dict[str, Any]]] = None,
    batch_id: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Execute an atomic transaction for batch ingestion:
    - Inserts all canonical records
    - Records all duplicate events into duplicate_audit
    - If any database error occurs, rolls back entirely.
    """
    close_after = False
    manage_tx = False
    if conn is None:
        conn = get_connection(db_path)
        conn.isolation_level = None
        close_after = True
        manage_tx = True

    imported_ids: List[str] = []
    duplicate_count = len(duplicates or [])

    try:
        if manage_tx:
            conn.execute("BEGIN IMMEDIATE;")

        for rec in records:
            # Ensure import_batch_id is attached if provided
            if batch_id and not rec.get("import_batch_id"):
                rec["import_batch_id"] = batch_id
            rec_id = insert_record(rec, conn=conn)
            imported_ids.append(rec_id)

        if duplicates:
            for dup in duplicates:
                record_duplicate(
                    batch_id=batch_id,
                    matched_record_id=dup["matched_record_id"],
                    match_reason=dup["match_reason"],
                    duplicate_source=dup.get("source"),
                    duplicate_source_type=dup.get("source_type"),
                    duplicate_source_id=dup.get("source_id"),
                    duplicate_original_url=dup.get("original_url"),
                    duplicate_content_hash=dup.get("content_hash"),
                    is_synthetic=bool(dup.get("is_synthetic", False)),
                    conn=conn,
                )

        if batch_id:
            # Update batch summary atomically
            conn.execute(
                """
                UPDATE import_batches
                SET records_imported = records_imported + ?,
                    records_duplicate = records_duplicate + ?,
                    records_processed = records_processed + ?
                WHERE batch_id = ?;
                """,
                (len(imported_ids), duplicate_count, len(imported_ids) + duplicate_count, batch_id),
            )

        if manage_tx:
            conn.execute("COMMIT;")

        return {
            "success": True,
            "imported_count": len(imported_ids),
            "duplicate_count": duplicate_count,
            "imported_ids": imported_ids,
        }
    except Exception as e:
        if manage_tx:
            conn.execute("ROLLBACK;")
        if batch_id:
            try:
                log_event(batch_id, "ERROR", f"Transaction rolled back due to error: {str(e)}", db_path=db_path)
            except Exception:
                pass
        raise e
    finally:
        if close_after:
            conn.close()


def get_record_by_id(
    record_id: str,
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve a single canonical record by record_id."""
    conn = get_connection(db_path)
    try:
        cur = conn.execute("SELECT * FROM records WHERE record_id = ?;", (record_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_database_summary(
    include_synthetic: bool = False,
    db_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Get aggregated counts for the Data Collection Centre Overview.
    By default, synthetic records are excluded from research metrics.
    """
    conn = get_connection(db_path)
    try:
        synthetic_filter = "" if include_synthetic else "WHERE is_synthetic = 0"
        where_or_and = "WHERE" if include_synthetic else "AND"

        # Total records
        total_res = conn.execute(f"SELECT COUNT(*) as cnt FROM records {synthetic_filter};").fetchone()
        total_records = total_res["cnt"] if total_res else 0

        # Customer discussion records
        cust_res = conn.execute(
            f"SELECT COUNT(*) as cnt FROM records WHERE source_type = 'customer_discussion' {'AND is_synthetic = 0' if not include_synthetic else ''};"
        ).fetchone()
        customer_discussions = cust_res["cnt"] if cust_res else 0

        # Media records
        media_res = conn.execute(
            f"SELECT COUNT(*) as cnt FROM records WHERE source_type = 'media' {'AND is_synthetic = 0' if not include_synthetic else ''};"
        ).fetchone()
        media_records = media_res["cnt"] if media_res else 0

        # Total duplicates logged
        duplicate_filter = "" if include_synthetic else """
            WHERE d.is_synthetic = 0 AND r.is_synthetic = 0
              AND COALESCE(b.is_synthetic, 0) = 0
        """
        dup_res = conn.execute(f"""
            SELECT COUNT(*) as cnt FROM duplicate_audit d
            JOIN records r ON r.record_id = d.matched_record_id
            LEFT JOIN import_batches b ON b.batch_id = d.batch_id
            {duplicate_filter};
        """).fetchone()
        total_duplicates = dup_res["cnt"] if dup_res else 0

        # Latest batch info
        batch_res = conn.execute(
            f"""
            SELECT batch_id, started_at, records_imported, records_duplicate, records_invalid
            FROM import_batches
            {synthetic_filter}
            ORDER BY started_at DESC LIMIT 1;
            """
        ).fetchone()
        latest_batch = dict(batch_res) if batch_res else None

        # Most recent collection timestamp
        latest_ts_res = conn.execute(
            f"SELECT MAX(collected_at) as latest_ts FROM records {synthetic_filter};"
        ).fetchone()
        latest_collection_ts = latest_ts_res["latest_ts"] if latest_ts_res else None

        return {
            "total_records": total_records,
            "customer_discussions": customer_discussions,
            "media_records": media_records,
            "total_duplicates_logged": total_duplicates,
            "latest_collection_timestamp": latest_collection_ts,
            "latest_batch": latest_batch,
        }
    finally:
        conn.close()


def get_batches(limit: int = 50, db_path: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
    """Retrieve import batch history ordered by latest started_at."""
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            SELECT * FROM import_batches
            ORDER BY started_at DESC
            LIMIT ?;
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_duplicate_audits(
    batch_id: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """Retrieve duplicate audit log entries."""
    conn = get_connection(db_path)
    try:
        if batch_id:
            cur = conn.execute(
                """
                SELECT * FROM duplicate_audit
                WHERE batch_id = ?
                ORDER BY attempted_at DESC
                LIMIT ?;
                """,
                (batch_id, limit),
            )
        else:
            cur = conn.execute(
                """
                SELECT * FROM duplicate_audit
                ORDER BY attempted_at DESC
                LIMIT ?;
                """,
                (limit,),
            )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
