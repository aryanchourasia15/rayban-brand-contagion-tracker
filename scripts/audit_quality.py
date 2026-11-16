"""
Data-Quality Audit Script — Ray-Ban Customer Trust Intelligence
Runs live GDELT fetch, inspects in-batch duplicates, verifies headline dedup safety,
and classifies article relevance. Writes findings to stdout.
"""
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- repo root on path ---
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.cleaner import canonicalize_url, normalize_text
from src.data.connectors.gdelt import fetch_gdelt_articles, transform_gdelt_article_to_record


# ---------------------------------------------------------------------------
# 1.  Relevance classification rules (keyword-based, no LLMs)
# ---------------------------------------------------------------------------
RELEVANT_TERMS = [
    "privacy", "surveillance", "recording", "facial recognition",
    "spy", "creepy", "data collection", "consent", "wiretap",
    "tracking", "identified", "identity", "controversy", "banned",
]
CONTEXTUAL_TERMS = [
    "ray-ban meta", "rayban meta", "meta glasses", "smart glasses",
    "ai glasses", "ar glasses", "wearable camera",
]


def classify_relevance(title: str, url: str) -> str:
    """
    Classify as 'relevant', 'contextual', or 'irrelevant'.
    - relevant:   directly about privacy/recording controversy for Ray-Ban Meta
    - contextual: mentions Ray-Ban Meta but in a broader tech/lifestyle context
    - irrelevant: only tangentially related (gift guides, unrelated products)
    """
    combined = (title + " " + url).lower()

    has_privacy = any(t in combined for t in RELEVANT_TERMS)
    has_rayban_meta = any(t in combined for t in CONTEXTUAL_TERMS)

    if has_privacy and has_rayban_meta:
        return "relevant"
    if has_rayban_meta:
        return "contextual"
    if has_privacy:
        return "contextual"
    return "irrelevant"


# ---------------------------------------------------------------------------
# 2.  Duplicate-reason simulation (mirrors DeduplicationEngine tier logic)
# ---------------------------------------------------------------------------
def find_duplicate_reason(candidate, seen_source_ids, seen_canonical_urls, seen_hashes):
    """
    Simulate the 3-tier dedup against in-batch accumulated state.
    Returns match_reason string or None.
    """
    source_id = candidate.get("source_id", "")
    canonical_url = candidate.get("canonical_url", "")
    source = candidate.get("source", "")
    source_type = candidate.get("source_type", "")
    content_hash = candidate.get("content_hash", "")

    # Tier 1 — source_id within same source
    key1 = (source, source_id)
    if source_id and key1 in seen_source_ids:
        return "source_id"

    # Tier 2 — canonical_url
    if canonical_url and canonical_url in seen_canonical_urls:
        return "canonical_url"

    # Tier 3 — content_hash within same source+source_type
    key3 = (source, source_type, content_hash)
    if content_hash and key3 in seen_hashes:
        return "content_hash"

    return None


def compute_content_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 3.  Main audit
# ---------------------------------------------------------------------------
def run_audit():
    # GDELT requires hyphenated words to be quoted; use phrase query
    query = '"Ray-Ban Meta"'
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=30)

    print("=" * 70)
    print("RAY-BAN CUSTOMER TRUST INTELLIGENCE — DATA QUALITY AUDIT")
    print(f"Query : {query!r}")
    print(f"Window: last 30 days  ({start_dt.date()} → {end_dt.date()})")
    print("=" * 70)

    # --- Fetch ---
    print("\n[1/4] Fetching articles from GDELT …")
    result = fetch_gdelt_articles(query, start_date=start_dt, end_date=end_dt, max_records=10)
    if not result["success"]:
        print(f"  ERROR: {result.get('error')}")
        sys.exit(1)

    raw_articles = result["articles"]
    print(f"  Articles returned by API: {len(raw_articles)}")
    if result.get("warning"):
        print(f"  WARNING: {result['warning']}")

    # --- Transform ---
    candidates = []
    invalid_count = 0
    for art in raw_articles:
        rec = transform_gdelt_article_to_record(art, query=query)
        if rec:
            # Attach canonical URL and content_hash (normally done inside DeduplicationEngine)
            canon_url, domain = canonicalize_url(rec.get("original_url", ""))
            rec["canonical_url"] = canon_url
            rec["domain"] = domain
            norm = normalize_text(rec["text"])
            rec["normalized_text"] = norm
            rec["content_hash"] = compute_content_hash(norm)
            candidates.append(rec)
        else:
            invalid_count += 1

    print(f"  Valid candidates: {len(candidates)},  Invalid (rejected): {invalid_count}")

    # --- In-batch duplicate simulation ---
    print("\n[2/4] Simulating in-batch deduplication …")
    seen_source_ids = set()
    seen_canonical_urls = set()
    seen_hashes = set()

    unique_records = []
    duplicate_records = []

    for rec in candidates:
        reason = find_duplicate_reason(rec, seen_source_ids, seen_canonical_urls, seen_hashes)
        if reason:
            duplicate_records.append((rec, reason))
        else:
            unique_records.append(rec)
            # Register in seen sets
            source = rec.get("source", "")
            source_type = rec.get("source_type", "")
            source_id = rec.get("source_id", "")
            canon_url = rec.get("canonical_url", "")
            content_hash = rec.get("content_hash", "")
            if source_id:
                seen_source_ids.add((source, source_id))
            if canon_url:
                seen_canonical_urls.add(canon_url)
            if content_hash:
                seen_hashes.add((source, source_type, content_hash))

    print(f"  Unique: {len(unique_records)},  In-batch duplicates: {len(duplicate_records)}")

    # --- Report duplicates ---
    print("\n--- IN-BATCH DUPLICATES ---")
    if not duplicate_records:
        print("  No in-batch duplicates detected.")
    for i, (dup, reason) in enumerate(duplicate_records, 1):
        print(f"\n  Duplicate #{i}")
        print(f"    Title       : {dup.get('title', '(none)')}")
        print(f"    Original URL: {dup.get('original_url', '(none)')}")
        print(f"    Canonical URL: {dup.get('canonical_url', '(none)')}")
        print(f"    Match reason: {reason}")

    # --- Headline-only dedup safety check ---
    print("\n[3/4] Headline collision safety check …")
    print("  Checking whether distinct canonical URLs are incorrectly merged via identical headlines …")

    # Group unique records by normalised title
    by_title: dict = {}
    for rec in unique_records + [d for d, _ in duplicate_records]:
        norm_title = normalize_text(rec.get("title", "")).lower().strip()
        by_title.setdefault(norm_title, []).append(rec)

    headline_collisions = {t: recs for t, recs in by_title.items() if len(recs) > 1}

    if not headline_collisions:
        print("  PASS — No identical headlines found across distinct records.")
    else:
        for title, recs in headline_collisions.items():
            urls = [r.get("canonical_url") for r in recs]
            unique_urls = set(urls)
            if len(unique_urls) > 1:
                print(f"  WARNING — Headline shared by {len(recs)} records with DIFFERENT canonical URLs:")
                print(f"    Title: {title!r}")
                for r in recs:
                    print(f"      URL: {r.get('canonical_url')}")
            else:
                # Same canonical URL → legitimate in-batch duplicate
                print(f"  INFO — Headline shared by {len(recs)} records with the SAME canonical URL (legitimate dup):")
                print(f"    Title: {title!r}  |  URL: {list(unique_urls)[0]}")

    # --- Relevance classification of all 10 articles ---
    print("\n[4/4] Relevance classification of all retrieved articles …")
    all_records = unique_records + [d for d, _ in duplicate_records]
    # Sort by original order (index in candidates)
    all_records_ordered = candidates  # original order

    counts = {"relevant": 0, "contextual": 0, "irrelevant": 0}
    print(f"\n  {'#':<3} {'Relevance':<12} {'Domain':<30} Title")
    print(f"  {'-'*3} {'-'*12} {'-'*30} {'-'*40}")
    for i, rec in enumerate(all_records_ordered, 1):
        relevance = classify_relevance(rec.get("title", ""), rec.get("original_url", ""))
        counts[relevance] += 1
        title_short = rec.get("title", "")[:55]
        domain = rec.get("domain", "")[:28]
        print(f"  {i:<3} {relevance:<12} {domain:<30} {title_short}")

    print(f"\n  Summary: relevant={counts['relevant']}, contextual={counts['contextual']}, irrelevant={counts['irrelevant']}")

    # --- Detailed listing of unique records ---
    print("\n--- ALL UNIQUE RECORDS (FULL DETAILS) ---")
    for i, rec in enumerate(unique_records, 1):
        relevance = classify_relevance(rec.get("title", ""), rec.get("original_url", ""))
        print(f"\n  Unique Record #{i}")
        print(f"    Title       : {rec.get('title')}")
        print(f"    Domain      : {rec.get('domain')}")
        print(f"    Original URL: {rec.get('original_url')}")
        print(f"    Canonical URL: {rec.get('canonical_url')}")
        print(f"    Published   : {rec.get('published_at', 'unknown')}")
        print(f"    Relevance   : {relevance}")

    print("\n" + "=" * 70)
    print("AUDIT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    run_audit()
