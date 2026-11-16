"""Small, uncached adapters for explorer queries and confirmed news previews."""
from datetime import timedelta

import pandas as pd

from src.data.db import get_connection, start_batch, finish_batch, log_event
from src.data.deduplicator import DeduplicationEngine


def load_records(*, sources=(), source_types=(), relevance_flags=(), search="",
                 published_from=None, published_to=None, collected_from=None,
                 collected_to=None, db_path=None):
    clauses, params = ["is_synthetic = 0"], []
    for column, values in (("source", sources), ("source_type", source_types),
                           ("relevance_flag", relevance_flags)):
        if values:
            clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
            params.extend(values)
    if search:
        clauses.append("(instr(lower(text), lower(?)) > 0 OR instr(lower(title), lower(?)) > 0)")
        params.extend([search, search])
    for column, lower, upper in (("published_at", published_from, published_to),
                                  ("collected_at", collected_from, collected_to)):
        if lower:
            clauses.append(f"julianday({column}) >= julianday(?)")
            params.append(lower.isoformat())
        if upper:
            clauses.append(f"julianday({column}) < julianday(?)")
            params.append((upper + timedelta(days=1)).isoformat())
    conn = get_connection(db_path)
    try:
        return pd.read_sql_query(
            "SELECT record_id, source, source_type, title, text, canonical_url, original_url, "
            "published_at, collected_at, relevance_flag, collection_method, import_batch_id "
            "FROM records WHERE " + " AND ".join(clauses) + " ORDER BY collected_at DESC, record_id",
            conn, params=params,
        )
    finally:
        conn.close()


def load_history(db_path=None):
    conn = get_connection(db_path)
    try:
        return pd.read_sql_query(
            "SELECT batch_id, started_at, completed_at, source, collection_method, status, "
            "records_processed, records_imported, records_duplicate, records_invalid, error_details "
            "FROM import_batches WHERE is_synthetic = 0 ORDER BY started_at DESC", conn,
        )
    finally:
        conn.close()


def import_news_preview(records, query, invalid_count=0, db_path=None):
    """Save the exact reviewed snapshot without a second API request."""
    batch = start_batch("News", "GDELT", batch_name=f"gdelt_{query[:30]}", db_path=db_path)
    try:
        result = DeduplicationEngine(db_path).ingest_batch_safely(records, batch_id=batch)
    except Exception as exc:
        finish_batch(batch, status="failed", error_details=str(exc), db_path=db_path)
        log_event(batch, "ERROR", str(exc), db_path=db_path)
        raise
    finish_batch(batch, status="partial" if invalid_count else "completed",
                 processed=len(records) + invalid_count, imported=result["imported"],
                 duplicate=result["duplicate"], invalid=invalid_count, db_path=db_path)
    log_event(batch, "INFO", f"Imported reviewed GDELT preview for {query}", db_path=db_path)
    return {"imported": result["imported"], "duplicates": result["duplicate"], "invalid": invalid_count}
