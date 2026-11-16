"""
Ray-Ban Customer Trust Intelligence
GDELT DOC 2.0 News Ingestion Connector
"""

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from dateutil import parser as date_parser

from src.config import (
    DEFAULT_GDELT_QUERIES,
    GDELT_BASE_URL,
    GDELT_DEFAULT_MAX_RECORDS,
    GDELT_HISTORICAL_WINDOW_DAYS,
    GDELT_REQUEST_TIMEOUT_SECONDS,
)
from src.data.cleaner import canonicalize_url, parse_date_to_utc_iso
from src.data.classifier import classify_relevance
from src.data.db import finish_batch, log_event, start_batch
from src.data.deduplicator import DeduplicationEngine


def format_gdelt_datetime(date_val: Union[str, datetime]) -> str:
    """
    Format a date into GDELT API format (YYYYMMDDHHMMSS).
    Converts timezone-aware dates to UTC.
    Raises ValueError if date_val is invalid or cannot be parsed.
    """
    if date_val is None:
        raise ValueError("Date value cannot be None.")

    if isinstance(date_val, datetime):
        if date_val.tzinfo is not None:
            date_val = date_val.astimezone(timezone.utc)
        return date_val.strftime("%Y%m%d%H%M%S")

    date_str = str(date_val).strip()
    if not date_str:
        raise ValueError("Date string cannot be empty.")

    if date_str.isdigit() and len(date_str) in (8, 14):
        return date_str.ljust(14, "0")

    try:
        parsed = date_parser.parse(date_str)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.strftime("%Y%m%d%H%M%S")
    except Exception as e:
        raise ValueError(f"Invalid date format '{date_val}': {str(e)}")


def validate_gdelt_dates(
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Validate and format date range for GDELT API.
    - Explicitly rejects invalid dates (raises ValueError).
    - Rejects start_date > end_date (raises ValueError).
    - Enforces the documented ~3-month (90 days) rolling window limitation of GDELT ArticleList.

    Returns:
        (formatted_start, formatted_end, warning_message_or_none)
    """
    formatted_start = format_gdelt_datetime(start_date) if start_date is not None else None
    formatted_end = format_gdelt_datetime(end_date) if end_date is not None else None

    if formatted_start and formatted_end:
        if formatted_start > formatted_end:
            raise ValueError(
                f"start_date ({start_date}) cannot be after end_date ({end_date})."
            )

    warning = None
    if formatted_start:
        try:
            start_dt = datetime.strptime(formatted_start, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            cutoff = datetime.now(timezone.utc) - timedelta(days=GDELT_HISTORICAL_WINDOW_DAYS)
            if start_dt < cutoff:
                warning = (
                    f"GDELT ArticleList provides a rolling ~{GDELT_HISTORICAL_WINDOW_DAYS}-day "
                    f"(~3 months) recent news window. Start date ({start_dt.strftime('%Y-%m-%d')}) "
                    f"pre-dates this coverage window. Historical data from 2023–2026 must be "
                    "imported via CSV/JSON rather than relying exclusively on GDELT."
                )
        except Exception:
            pass

    return formatted_start, formatted_end, warning


def fetch_gdelt_articles(
    query: str,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
    max_records: int = GDELT_DEFAULT_MAX_RECORDS,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """
    Query the free GDELT DOC 2.0 API in JSON mode with retry logic and error handling.
    Rejects unsupported historical requests before making API calls.

    Returns:
        Dict containing success, articles list, total_found, warning, or error.
    """
    if not query or not str(query).strip():
        raise ValueError("GDELT query cannot be empty.")

    formatted_start, formatted_end, date_warning = validate_gdelt_dates(start_date, end_date)

    # Reject unsupported historical requests before making API calls
    if formatted_start:
        start_dt = datetime.strptime(formatted_start, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=GDELT_HISTORICAL_WINDOW_DAYS)
        if start_dt < cutoff:
            return {
                "success": False,
                "articles": [],
                "total_found": 0,
                "query": query,
                "warning": date_warning,
                "error": (
                    f"Unsupported historical request: GDELT DOC 2.0 ArticleList only supports recent news "
                    f"(rolling ~{GDELT_HISTORICAL_WINDOW_DAYS}-day window). Requested start date "
                    f"({start_dt.strftime('%Y-%m-%d')}) cannot be retrieved via this endpoint. "
                    "Please import historical records (2023–2026) using the CSV/JSON importer."
                ),
            }

    # GDELT max records is 250 per call
    clamped_max = min(max(1, max_records), 250)

    params: Dict[str, str] = {
        "query": str(query).strip(),
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(clamped_max),
        "sort": "DateDesc",
    }
    if formatted_start:
        params["startdatetime"] = formatted_start
    if formatted_end:
        params["enddatetime"] = formatted_end

    http = session or requests.Session()
    headers = {"User-Agent": "RayBanCustomerTrustIntelligence/1.0 (Academic Research; HEC Paris)"}

    last_error: Optional[str] = None

    for attempt in range(max_retries):
        try:
            resp = http.get(
                GDELT_BASE_URL,
                params=params,
                headers=headers,
                timeout=GDELT_REQUEST_TIMEOUT_SECONDS,
            )

            # Retry on transient server errors or rate limiting
            if resp.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {resp.status_code}: {resp.reason}"
                time.sleep(backoff_factor * (2**attempt))
                continue

            resp.raise_for_status()

            raw_text = resp.text.strip()
            # GDELT returns empty string or empty object if no articles matched
            if not raw_text or raw_text == "{}":
                return {
                    "success": True,
                    "articles": [],
                    "total_found": 0,
                    "query": query,
                    "warning": date_warning,
                }

            try:
                data = resp.json()
            except Exception:
                return {
                    "success": False,
                    "articles": [],
                    "total_found": 0,
                    "query": query,
                    "warning": date_warning,
                    "error": f"GDELT returned non-JSON response: {raw_text[:200]}",
                }

            articles = data.get("articles", []) if isinstance(data, dict) else []
            return {
                "success": True,
                "articles": articles,
                "total_found": len(articles),
                "query": query,
                "warning": date_warning,
            }

        except (requests.RequestException, TimeoutError) as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                time.sleep(backoff_factor * (2**attempt))

    return {
        "success": False,
        "articles": [],
        "total_found": 0,
        "query": query,
        "warning": date_warning,
        "error": f"GDELT request failed after {max_retries} retries: {last_error}",
    }


def transform_gdelt_article_to_record(
    article: Dict[str, Any],
    query: str,
    is_synthetic: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Transform a raw GDELT article into a canonical record for deduplication and storage.
    Validates:
    - Must be a dictionary
    - Non-empty title
    - Valid HTTP(S) URL with extractable domain
    Returns None if malformed or invalid.
    """
    if not isinstance(article, dict):
        return None

    title = str(article.get("title", "")).strip() if article.get("title") else ""
    if not title:
        return None

    raw_url = str(article.get("url", "")).strip() if article.get("url") else ""
    if not raw_url:
        return None

    lowered_url = raw_url.lower()
    if not (lowered_url.startswith("http://") or lowered_url.startswith("https://")):
        return None

    canonical_url, domain = canonicalize_url(raw_url)
    if not canonical_url or not domain:
        return None

    published_at = parse_date_to_utc_iso(article.get("seendate"), source="GDELT")
    if published_at is None:
        return None
    relevance_flag = classify_relevance(title=title, url=raw_url, text=title)

    # Store full API payload in raw_payload
    payload = dict(article)
    payload["search_query"] = query

    return {
        "source": "News",
        "source_type": "media",
        "source_id": raw_url,
        "title": title,
        "text": title,  # Headline is the unmodified text provided by GDELT ArticleList
        "original_url": raw_url,
        "published_at": published_at,
        "domain": domain,
        "collection_method": "GDELT",
        "is_synthetic": 1 if is_synthetic else 0,
        "raw_payload": payload,
        "relevance_flag": relevance_flag,
    }


def search_gdelt(
    query: str,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
    max_records: int = GDELT_DEFAULT_MAX_RECORDS,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """Execute search against GDELT DOC 2.0 API."""
    return fetch_gdelt_articles(
        query=query,
        start_date=start_date,
        end_date=end_date,
        max_records=max_records,
        session=session,
    )


def preview_gdelt(
    query: str,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
    max_records: int = 10,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """Preview news records from GDELT without saving to the database."""
    res = fetch_gdelt_articles(
        query=query,
        start_date=start_date,
        end_date=end_date,
        max_records=max_records,
        session=session,
    )
    if not res["success"]:
        return res

    transformed = []
    invalid_count = 0
    for art in res["articles"]:
        rec = transform_gdelt_article_to_record(art, query=query)
        if rec:
            transformed.append(rec)
        else:
            invalid_count += 1

    return {
        "success": True,
        "query": query,
        "total_found": res["total_found"],
        "preview_records": transformed[:max_records],
        "invalid_count": invalid_count,
        "warning": res.get("warning"),
    }


def import_gdelt(
    query: str,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
    max_records: int = GDELT_DEFAULT_MAX_RECORDS,
    is_synthetic: bool = False,
    batch_name: Optional[str] = None,
    session: Optional[requests.Session] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Execute news search, validate, and atomically ingest articles into SQLite database.
    """
    batch_id = start_batch(
        source="News",
        collection_method="GDELT",
        batch_name=batch_name or f"gdelt_{query[:30]}",
        is_synthetic=is_synthetic,
        db_path=db_path,
    )

    log_event(batch_id, "INFO", f"Initiating GDELT collection for query: '{query}'", db_path=db_path)

    try:
        # Fetch articles
        search_res = fetch_gdelt_articles(
            query=query,
            start_date=start_date,
            end_date=end_date,
            max_records=max_records,
            session=session,
        )

        if not search_res["success"]:
            err_msg = search_res.get("error", "Unknown GDELT error")
            finish_batch(
                batch_id=batch_id,
                status="failed",
                error_details=err_msg,
                db_path=db_path,
            )
            log_event(batch_id, "ERROR", f"GDELT collection failed: {err_msg}", db_path=db_path)
            raise RuntimeError(err_msg)

        raw_articles = search_res["articles"]
        valid_candidates = []
        invalid_count = 0

        for art in raw_articles:
            if not isinstance(art, dict):
                invalid_count += 1
                continue
            rec = transform_gdelt_article_to_record(art, query=query, is_synthetic=is_synthetic)
            if rec:
                valid_candidates.append(rec)
            else:
                invalid_count += 1

        # Concurrency-safe deduplication and atomic insertion
        engine = DeduplicationEngine(db_path=db_path)
        ingest_res = engine.ingest_batch_safely(valid_candidates, batch_id=batch_id)

        imported = ingest_res["imported"]
        duplicates = ingest_res["duplicate"]

        finish_batch(
            batch_id=batch_id,
            status="completed" if invalid_count == 0 else "partial",
            processed=len(raw_articles),
            imported=imported,
            duplicate=duplicates,
            invalid=invalid_count,
            error_details=f"{invalid_count} articles rejected during validation." if invalid_count else search_res.get("warning"),
            db_path=db_path,
        )

        log_event(
            batch_id,
            "INFO",
            f"GDELT batch {batch_id} complete: {imported} imported, {duplicates} duplicate, {invalid_count} invalid.",
            db_path=db_path,
        )

        return {
            "success": True,
            "batch_id": batch_id,
            "query": query,
            "processed": len(raw_articles),
            "imported": imported,
            "duplicates": duplicates,
            "invalid": invalid_count,
            "warning": search_res.get("warning"),
            "imported_ids": ingest_res.get("imported_ids", []),
        }

    except Exception as e:
        finish_batch(
            batch_id=batch_id,
            status="failed",
            error_details=str(e),
            db_path=db_path,
        )
        log_event(batch_id, "ERROR", f"Batch {batch_id} aborted: {str(e)}", db_path=db_path)
        raise e
