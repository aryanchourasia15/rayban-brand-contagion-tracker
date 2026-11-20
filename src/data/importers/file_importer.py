"""
Ray-Ban Customer Trust Intelligence
CSV and JSON File Importer with Column Auto-Mapping, Validation, and Safe Ingestion
"""

import csv
import io
import json
from datetime import timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.config import (
    VALID_COLLECTION_METHODS,
    VALID_SOURCE_TYPES,
    VALID_SOURCES,
)
from src.data.cleaner import canonicalize_url, parse_date_to_utc_iso
from src.data.db import finish_batch, log_event, start_batch
from src.data.deduplicator import DeduplicationEngine

# Common aliases for automatic column detection
DEFAULT_COLUMN_ALIASES: Dict[str, List[str]] = {
    "text": ["text", "body", "comment", "content", "message", "review", "post", "description"],
    "title": ["title", "headline", "subject", "header"],
    "published_at": ["date", "created", "created_at", "timestamp", "published_at", "datetime", "time", "published"],
    "url": ["url", "permalink", "link", "source_url", "uri", "web_url"],
    "source": ["source", "platform", "origin"],
    "source_id": ["id", "source_id", "post_id", "comment_id", "article_id", "uid"],
    "source_type": ["source_type", "type", "category"],
    "subreddit": ["subreddit", "sub"],
}


def declared_synthetic_row(row):
    """Recognise explicit simulation markers, without changing ingestion mode."""
    return isinstance(row, dict) and (
        str(row.get("is_synthetic", "")).strip().lower() in ("true", "1", "yes") or
        str(row.get("source_kind", "")).strip().lower() == "ai-generated simulation")


def detect_column_mapping(columns: List[str]) -> Dict[str, str]:
    """
    Automatically detect canonical field mappings from a list of column names.
    Returns:
        Dict[canonical_field, file_column_name]
    """
    mapping: Dict[str, str] = {}
    normalized_cols = {col.strip().lower().replace(" ", "_"): col for col in columns if col}

    for canonical_field, aliases in DEFAULT_COLUMN_ALIASES.items():
        for alias in aliases:
            norm_alias = alias.lower()
            if norm_alias in normalized_cols:
                mapping[canonical_field] = normalized_cols[norm_alias]
                break

    return mapping


def parse_file_to_rows(
    file_input: Union[str, Path, bytes, io.IOBase],
    file_format: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parse a CSV or JSON file/payload into a list of row dictionaries and headers.
    Supports:
    - CSV files (handling UTF-8, UTF-8 with BOM, Latin-1 fallback)
    - JSON files (arrays `[...]`, or wrapped `{"records": [...]}`, `{"data": [...]}`)

    Returns:
        (rows, headers)
    """
    raw_content: str = ""

    # 1. Read input into string with encoding resilience
    if isinstance(file_input, (str, Path)) and (isinstance(file_input, Path) or Path(file_input).exists()):
        path = Path(file_input)
        if not file_format:
            file_format = path.suffix.lstrip(".").lower()
        with open(path, "rb") as f:
            bytes_data = f.read()
    elif isinstance(file_input, bytes):
        bytes_data = file_input
    elif hasattr(file_input, "read"):
        content = file_input.read()
        bytes_data = content.encode("utf-8") if isinstance(content, str) else content
    elif isinstance(file_input, str):
        # In-memory string content
        raw_content = file_input
        bytes_data = b""
    else:
        raise ValueError(f"Unsupported file input type: {type(file_input)}")

    if bytes_data:
        # Decode with UTF-8 BOM detection, fallback to UTF-8 then Latin-1
        try:
            raw_content = bytes_data.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                raw_content = bytes_data.decode("utf-8")
            except UnicodeDecodeError:
                raw_content = bytes_data.decode("latin-1")

    # Strip any leading Unicode BOM character from string and whitespace
    raw_content = raw_content.lstrip("\ufeff").strip()
    if not raw_content:
        return [], []

    # Detect format if not specified
    if not file_format:
        if raw_content.startswith(("[", "{")):
            file_format = "json"
        else:
            file_format = "csv"

    # 2. Parse JSON
    if file_format == "json":
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed JSON: {str(e)}")

        if isinstance(data, list):
            raw_rows = data
        elif isinstance(data, dict):
            if "records" in data and isinstance(data["records"], list):
                raw_rows = data["records"]
            elif "data" in data and isinstance(data["data"], list):
                raw_rows = data["data"]
            elif "items" in data and isinstance(data["items"], list):
                raw_rows = data["items"]
            else:
                raw_rows = [data]
        else:
            raise ValueError("JSON must contain an array or an object with a 'records' list.")

        # Preserve all rows (including non-dict entries) so validation can report them with row numbers
        rows = list(raw_rows)
        headers: List[str] = []
        for r in rows:
            if isinstance(r, dict):
                for k in r.keys():
                    if str(k) not in headers:
                        headers.append(str(k))
        return rows, headers

    # 3. Parse CSV
    elif file_format == "csv":
        # Handle delimiter sniffing
        sniffer = csv.Sniffer()
        sample = raw_content[:4096]
        try:
            dialect = sniffer.sniff(sample)
        except Exception:
            dialect = csv.excel

        reader = csv.DictReader(io.StringIO(raw_content), dialect=dialect)
        headers = [str(h).lstrip("\ufeff").strip() for h in (reader.fieldnames or []) if h]
        rows = []
        for r in reader:
            cleaned_row = {str(k).lstrip("\ufeff").strip(): v for k, v in r.items() if k is not None}
            rows.append(cleaned_row)
        return rows, headers

    else:
        raise ValueError(f"Unsupported file format '{file_format}'. Only 'csv' and 'json' are supported.")


def validate_and_transform_rows(
    raw_rows: List[Dict[str, Any]],
    column_mapping: Optional[Dict[str, str]] = None,
    default_source: str = "Imported",
    default_source_type: str = "customer_discussion",
    day_first: Optional[bool] = None,
    default_tz: Optional[timezone] = None,
    is_synthetic: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Validate and transform parsed rows according to canonical schema.
    Extracts mapped fields, validates required fields and dates, and preserves
    unmapped fields into raw_payload.

    Returns:
        (valid_records, invalid_records)
    """
    if default_source not in VALID_SOURCES:
        raise ValueError(f"Invalid default_source: {default_source}. Must be in {VALID_SOURCES}")
    if default_source_type not in VALID_SOURCE_TYPES:
        raise ValueError(f"Invalid default_source_type: {default_source_type}. Must be in {VALID_SOURCE_TYPES}")

    mapping = column_mapping or {}
    valid_records: List[Dict[str, Any]] = []
    invalid_records: List[Dict[str, Any]] = []

    for idx, row in enumerate(raw_rows, start=1):
        # 1. Report non-object JSON entries as invalid rows with row numbers
        if not isinstance(row, dict):
            invalid_records.append(
                {
                    "row_number": idx,
                    "errors": [f"Row {idx} is not an object/dictionary (got {type(row).__name__})."],
                    "raw_data": {"value": str(row)},
                }
            )
            continue

        errors: List[str] = []
        # Explicit simulation markers must never be silently imported as real research.
        if declared_synthetic_row(row) and not is_synthetic:
            errors.append("AI-generated/synthetic rows require explicit is_synthetic=True ingestion; they cannot enter real research data.")

        # Helper to get mapped value
        def get_val(canonical_key: str, preserve: bool = False) -> Optional[str]:
            source_col = mapping.get(canonical_key, canonical_key)
            val = row.get(source_col)
            if val is None and canonical_key in row:
                val = row[canonical_key]
            if val is not None:
                val_str = str(val)
                return (val_str if preserve else val_str.strip()) if val_str.strip() else None
            return None

        # 2. Text is strictly required (keep original unmodified)
        text = get_val("text", preserve=True)
        if not text:
            errors.append("Missing or empty required field 'text'.")

        # 3. Source & Subreddit handling:
        # Subreddit names are metadata, not platform names.
        # Preserve subreddit separately and identify Reddit as the source.
        subreddit_col = mapping.get("subreddit", "subreddit")
        subreddit_val = row.get(subreddit_col) or row.get("sub")
        if subreddit_val is not None:
            subreddit_val = str(subreddit_val).strip()

        raw_source = get_val("source")
        source = default_source

        if subreddit_val:
            # Subreddit metadata present: unambiguously identify platform as Reddit
            source = "Reddit"
        elif raw_source:
            norm_source = raw_source.lower()
            if norm_source == "reddit" or norm_source.startswith("r/") or norm_source.startswith("/r/"):
                source = "Reddit"
                if norm_source.startswith("r/") or norm_source.startswith("/r/"):
                    subreddit_val = raw_source.lstrip("/")
            elif norm_source in ("news", "media"):
                source = "News"
            elif norm_source == "imported":
                source = "Imported"
            elif raw_source in VALID_SOURCES:
                source = raw_source
            else:
                errors.append(f"Invalid source '{raw_source}'. Must be one of {VALID_SOURCES}.")

        source_type = get_val("source_type") or default_source_type
        required_type = {"News": "media", "Reddit": "customer_discussion"}.get(source)
        if required_type:
            explicit_type = get_val("source_type")
            if explicit_type and explicit_type != required_type:
                errors.append(f"Source '{source}' requires source_type '{required_type}', got '{explicit_type}'.")
            source_type = required_type
        if source_type not in VALID_SOURCE_TYPES:
            errors.append(f"Invalid source_type '{source_type}'. Must be one of {VALID_SOURCE_TYPES}.")

        # 4. Date validation & unambiguous UTC conversion
        raw_date = get_val("published_at")
        published_at = None
        if raw_date:
            published_at = parse_date_to_utc_iso(
                raw_date,
                source=source,
                day_first=day_first,
                default_tz=default_tz,
            )
            if published_at is None:
                errors.append(
                    f"Invalid or ambiguous date format '{raw_date}'. "
                    "Ensure an unambiguous format or specify day_first / timezone."
                )

        orig_url = get_val("url")
        if orig_url and canonicalize_url(orig_url)[0] is None:
            errors.append(f"Invalid URL '{orig_url}': expected a valid HTTP(S) URL or domain.")

        # If any validation errors occurred, flag row as invalid
        if errors:
            invalid_records.append(
                {
                    "row_number": idx,
                    "errors": errors,
                    "raw_data": row,
                }
            )
            continue

        # 5. Extract other canonical fields
        title = get_val("title")
        source_id = get_val("source_id")

        # 6. Preserve the COMPLETE original imported row in raw_payload (including mapped fields)
        raw_payload = dict(row)
        if subreddit_val and "subreddit" not in raw_payload:
            raw_payload["subreddit"] = subreddit_val

        record = {
            "source": source,
            "source_type": source_type,
            "source_id": source_id,
            "title": title,
            "text": text,
            "original_url": orig_url,
            "published_at": published_at,
            "collection_method": "CSV import",
            "is_synthetic": 1 if is_synthetic else 0,
            "raw_payload": raw_payload,
            "_row_number": idx,
        }
        valid_records.append(record)

    return valid_records, invalid_records


def preview_import(
    file_input: Union[str, Path, bytes, io.IOBase],
    file_format: Optional[str] = None,
    column_mapping: Optional[Dict[str, str]] = None,
    default_source: str = "Imported",
    default_source_type: str = "customer_discussion",
    day_first: Optional[bool] = None,
    default_tz: Optional[timezone] = None,
    n_preview: int = 10,
) -> Dict[str, Any]:
    """
    Preview the first N records of an import, auto-detecting columns and running validation.
    """
    rows, headers = parse_file_to_rows(file_input, file_format=file_format)
    detected_mapping = detect_column_mapping(headers)

    active_mapping = dict(detected_mapping)
    if column_mapping:
        active_mapping.update(column_mapping)

    preview_rows = rows[:n_preview]
    valid_preview, invalid_preview = validate_and_transform_rows(
        preview_rows,
        column_mapping=active_mapping,
        default_source=default_source,
        default_source_type=default_source_type,
        day_first=day_first,
        default_tz=default_tz,
    )

    return {
        "total_rows_detected": len(rows),
        "headers": headers,
        "detected_mapping": detected_mapping,
        "active_mapping": active_mapping,
        "preview_valid_count": len(valid_preview),
        "preview_invalid_count": len(invalid_preview),
        "preview_records": valid_preview,
        "preview_invalid": invalid_preview,
    }


def import_file(
    file_input: Union[str, Path, bytes, io.IOBase],
    file_format: Optional[str] = None,
    column_mapping: Optional[Dict[str, str]] = None,
    default_source: str = "Imported",
    default_source_type: str = "customer_discussion",
    day_first: Optional[bool] = None,
    default_tz: Optional[timezone] = None,
    is_synthetic: bool = False,
    batch_name: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    End-to-end atomic file ingestion:
    - Parses CSV/JSON
    - Applies auto or manual column mappings
    - Validates rows and captures invalid rows
    - Ingests valid rows idempotently via DeduplicationEngine (BEGIN IMMEDIATE transaction)
    - Records batch metrics in import_batches
    - Returns structured summary
    """
    # 1. Parse file
    rows, headers = parse_file_to_rows(file_input, file_format=file_format)

    active_mapping = detect_column_mapping(headers)
    if column_mapping:
        active_mapping.update(column_mapping)

    # 2. Start batch tracking
    batch_id = start_batch(
        source=default_source,
        collection_method="CSV import",
        batch_name=batch_name or f"file_import_{default_source}_{len(rows)}rows",
        is_synthetic=is_synthetic,
        db_path=db_path,
    )

    log_event(batch_id, "INFO", f"Starting file import: {len(rows)} raw rows detected.", db_path=db_path)

    try:
        # 3. Validate rows
        valid_rows, invalid_rows = validate_and_transform_rows(
            rows,
            column_mapping=active_mapping,
            default_source=default_source,
            default_source_type=default_source_type,
            day_first=day_first,
            default_tz=default_tz,
            is_synthetic=is_synthetic,
        )

        # 4. Ingest valid records via concurrency-safe deduplication engine
        engine = DeduplicationEngine(db_path=db_path)
        ingest_result = engine.ingest_batch_safely(valid_rows, batch_id=batch_id)

        imported_count = ingest_result["imported"]
        duplicate_count = ingest_result["duplicate"]
        invalid_count = len(invalid_rows)

        # 5. Finish batch
        status = "completed" if invalid_count == 0 else "partial"
        finish_batch(
            batch_id=batch_id,
            status=status,
            processed=len(rows),
            imported=imported_count,
            duplicate=duplicate_count,
            invalid=invalid_count,
            error_details=f"{invalid_count} rows rejected during validation." if invalid_count else None,
            db_path=db_path,
        )

        log_event(
            batch_id,
            "INFO",
            f"Batch {batch_id} finished: {imported_count} imported, {duplicate_count} duplicate, {invalid_count} invalid.",
            db_path=db_path,
        )

        return {
            "success": True,
            "batch_id": batch_id,
            "processed": len(rows),
            "imported": imported_count,
            "duplicates": duplicate_count,
            "invalid": invalid_count,
            "errors": invalid_rows,
            "imported_ids": ingest_result.get("imported_ids", []),
        }
    except Exception as e:
        finish_batch(
            batch_id=batch_id,
            status="failed",
            processed=len(rows),
            imported=0,
            duplicate=0,
            invalid=len(rows),
            error_details=f"Batch ingestion failed: {str(e)}",
            db_path=db_path,
        )
        log_event(batch_id, "ERROR", f"Batch {batch_id} failed: {str(e)}", db_path=db_path)
        raise e


def generate_csv_template() -> str:
    """
    Generate a downloadable CSV template with canonical headers and instructions.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "text",
        "title",
        "published_at",
        "url",
        "source",
        "source_type",
        "source_id",
        "notes",
    ])
    writer.writerow([
        "I purchased the Ray-Ban Meta glasses but feel uncomfortable about the camera privacy light in public.",
        "Privacy concerns regarding camera light",
        "2024-03-15T14:30:00Z",
        "https://example.com/review/123",
        "Imported",
        "customer_discussion",
        "rev_001",
        "Sample unmapped column preserved in raw_payload",
    ])
    return output.getvalue()
