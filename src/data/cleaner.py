"""
Ray-Ban Customer Trust Intelligence
Data Cleaning, Normalization, URL Canonicalization, and UTC Date Parsing
"""

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dateutil import parser as date_parser

# Common marketing and tracking parameters to strip from URLs
TRACKING_PARAMS: Set[str] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "gclsrc",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref",
    "ref_src",
    "ref_url",
    "source",
    "trk",
    "_hsenc",
    "_hsmi",
    "mkt_tok",
    "vero_id",
}

# Short generic phrases that should never trigger text-hash deduplication
GENERIC_COMMENT_PHRASES: Set[str] = {
    "[deleted]",
    "[removed]",
    "yes",
    "no",
    "yeah",
    "agree",
    "agreed",
    "disagree",
    "thanks",
    "thank you",
    "thanks for sharing",
    "cool",
    "nice",
    "same",
    "same here",
    "true",
    "false",
    "wow",
    "lol",
    "lmao",
    "bump",
    "following",
    "+1",
    "interesting",
    "ok",
    "okay",
    "good point",
    "i agree",
    "i agree completely",
    "i agree completely with this statement",
}


def normalize_text(text: Optional[str]) -> str:
    """
    Normalize text consistently:
    - Unicode normalization using NFKC form (resolves compatibility characters, ligatures, fullwidth symbols)
    - Replaces smart/curly quotes with standard ASCII quotes
    - Collapses consecutive whitespace and line breaks to single spaces
    - Lowercases text for comparison and deterministic hashing

    Note: Original raw text must always be preserved separately in records.
    """
    if text is None:
        return ""

    if not isinstance(text, str):
        text = str(text)

    # 1. Unicode NFKC normalization
    normalized = unicodedata.normalize("NFKC", html.unescape(text))
    # Preserve whitespace boundaries; discard invisible control/format characters.
    normalized = "".join(
        char for char in normalized
        if char.isspace() or unicodedata.category(char) not in ("Cc", "Cf", "Cs")
    )

    # 2. Standardize quotation marks
    normalized = normalized.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

    # 3. Collapse whitespace and linebreaks
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # 4. Lowercase for hash and comparison
    return normalized.lower()


def compute_content_hash(normalized_text: str) -> str:
    """Compute deterministic SHA-256 hash of normalized text."""
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def is_generic_or_too_short(
    normalized_text: str,
    min_chars: int = 50,
    min_words: int = 8,
) -> bool:
    """
    Check if a comment is generic or too short to warrant hash-based deduplication.
    Prevents false-positive deduplication of distinct comments like 'agree', 'cool', 'thanks',
    or generic short phrases. Requires substantial length (>= 50 chars and >= 8 words)
    before content-hash deduplication is allowed.
    """
    cleaned = normalized_text.strip().lower()
    if not cleaned:
        return True

    # Exact match with generic phrases
    if cleaned in GENERIC_COMMENT_PHRASES:
        return True

    # Punctuation-stripped check against generic phrases
    no_punct = re.sub(r"[^\w\s]", "", cleaned).strip()
    if no_punct in GENERIC_COMMENT_PHRASES:
        return True

    # Check length thresholds (minimum 50 characters AND minimum 8 words)
    words = cleaned.split()
    if len(cleaned) < min_chars or len(words) < min_words:
        return True

    return False


def canonicalize_url(url: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Canonicalize a URL and extract its domain:
    - Handles leading/trailing whitespace
    - Adds https scheme if missing
    - Lowercases scheme and netloc/domain
    - Strips www. prefix for consistent domain matching
    - Removes standard default ports (:80, :443)
    - Validates hostname syntax (rejects invalid strings)
    - Strips tracking query parameters (utm_*, fbclid, etc.) while preserving content query params
    - Sorts remaining query parameters deterministically
    - Strips URL fragments (#...)
    - Normalizes multiple consecutive path slashes and trailing slashes

    Returns:
        (canonical_url, domain) or (None, None) if URL is invalid/malformed.
    """
    if not url or not isinstance(url, str):
        return None, None

    cleaned_url = url.strip()
    if not cleaned_url:
        return None, None
    if any(char.isspace() or unicodedata.category(char).startswith("C") for char in cleaned_url):
        return None, None

    # Handle missing scheme
    if "://" not in cleaned_url:
        cleaned_url = "https://" + cleaned_url

    try:
        parts = urlsplit(cleaned_url)
        # Accessing port also validates numeric syntax and the allowed range.
        parts.port
    except Exception:
        return None, None

    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        return None, None

    netloc = parts.netloc.lower()
    if not netloc:
        return None, None

    # Remove standard port specifications
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Validate hostname syntax: must not contain whitespace, must match hostname regex, and must have a dot
    if " " in netloc or not re.match(r"^[a-z0-9.-]+(:[0-9]+)?$", netloc) or "." not in netloc:
        return None, None
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
           for label in (parts.hostname or "").split(".")):
        return None, None

    # Clean domain and canonical host (strip www. for consistent canonical matching)
    if netloc.startswith("www."):
        netloc = netloc[4:]
    domain = netloc

    # Path normalization: collapse multiple slashes, strip trailing slash unless path is '/'
    path = re.sub(r"/{2,}", "/", parts.path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    if not path:
        path = "/"

    # Query parameters normalization: strip tracking params, sort keys
    query_params = parse_qsl(parts.query, keep_blank_values=False)
    filtered_params = [
        (k, v)
        for k, v in query_params
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    # Sort query parameters deterministically
    filtered_params.sort(key=lambda x: (x[0], x[1]))
    new_query = urlencode(filtered_params)

    # Always strip fragments (#) as they refer to page anchors
    canonical = urlunsplit((scheme, netloc, path, new_query, ""))
    return canonical, domain


def is_ambiguous_day_month(date_str: str) -> bool:
    """
    Check if a numeric date string has ambiguous day and month ordering
    (e.g., '03/04/2024', '03-04-2024', '03.04.2024') where both numbers are <= 12 and different.
    """
    cleaned = date_str.strip()
    match = re.match(r"^(\d{1,2})[/\.-](\d{1,2})[/\.-](\d{2,4})$", cleaned)
    if match:
        p1, p2 = int(match.group(1)), int(match.group(2))
        if 1 <= p1 <= 12 and 1 <= p2 <= 12 and p1 != p2:
            return True
    return False


def parse_date_to_utc_iso(
    date_val: Any,
    source: Optional[str] = None,
    day_first: Optional[bool] = None,
    default_tz: Optional[timezone] = None,
) -> Optional[str]:
    """
    Parse a date value into UTC ISO-8601 string (YYYY-MM-DDTHH:MM:SSZ).

    Documented Source-Specific Rules:
    - Reddit: Timestamps from Reddit API are Unix epoch seconds in UTC.
    - GDELT / News: Timestamps from GDELT DOC 2.0 API are formatted in UTC (YYYYMMDDTHHMMSSZ or YYYYMMDDHHMMSS).
    - If source in ('Reddit', 'GDELT', 'News'), default timezone is strictly UTC by specification.
    - For general or 'Imported' strings:
      * Strings with explicit timezone offsets ('Z', '+02:00', '-05:00') are parsed and converted to UTC.
      * Ambiguous numeric day/month orders (e.g. '03/04/2024' where both numbers <= 12) require an explicit
        `day_first` rule (True/False). If day_first is None, the ambiguous date is rejected (returns None).
      * Naive datetime strings without a timezone offset require an explicit `default_tz` or documented source.
        If both default_tz and source are None, the naive timestamp is rejected (returns None) rather than silently guessed.

    Returns:
        Formatted UTC ISO-8601 string, or None if invalid, missing, or ambiguous without documented rule.
        Never fabricates or invents a missing date.
    """
    if date_val is None:
        return None

    # Handle empty strings or pandas NA
    if isinstance(date_val, str):
        cleaned = date_val.strip()
        if not cleaned or cleaned.lower() in ("none", "null", "nan", "nat"):
            return None
        date_val = cleaned

    dt: Optional[datetime] = None

    # Determine effective default timezone based on source-specific documented rules
    effective_tz = default_tz
    if effective_tz is None and source in ("Reddit", "GDELT", "News"):
        effective_tz = timezone.utc

    # Handle numeric timestamps
    if isinstance(date_val, (int, float)):
        try:
            val = float(date_val)
            # If greater than 1e11, it's likely in milliseconds
            if val > 1e11:
                val = val / 1000.0
            dt = datetime.fromtimestamp(val, tz=timezone.utc)
        except Exception:
            return None

    elif isinstance(date_val, str):
        # Compact YYYYMMDDHHMMSS (14 digits) or YYYYMMDD (8 digits) format common in GDELT
        if date_val.isdigit() and len(date_val) == 14 and date_val.startswith(("19", "20")):
            try:
                dt = datetime.strptime(date_val, "%Y%m%d%H%M%S").replace(tzinfo=effective_tz or timezone.utc)
            except Exception:
                return None
        elif date_val.isdigit() and len(date_val) == 8 and date_val.startswith(("19", "20")):
            try:
                dt = datetime.strptime(date_val, "%Y%m%d").replace(tzinfo=effective_tz or timezone.utc)
            except Exception:
                return None
        # Numeric string timestamp check (Unix seconds or milliseconds)
        elif date_val.replace(".", "", 1).isdigit():
            try:
                val = float(date_val)
                if val > 1e11:
                    val = val / 1000.0
                dt = datetime.fromtimestamp(val, tz=timezone.utc)
            except Exception:
                return None
        else:
            # Check for ambiguous day/month format
            if is_ambiguous_day_month(date_val) and day_first is None:
                # Do not silently guess day/month order without an explicit rule
                return None

            try:
                # Use flexible date_parser with explicit dayfirst parameter
                df_param = False if day_first is None else day_first
                parsed = date_parser.parse(date_val, dayfirst=df_param)

                if parsed.tzinfo is None:
                    # Naive datetime: check if an explicit default timezone is documented
                    if effective_tz is None:
                        # Do not silently assume a timezone without a documented source rule
                        return None
                    dt = parsed.replace(tzinfo=effective_tz)
                else:
                    # Explicit timezone provided in string
                    dt = parsed.astimezone(timezone.utc)
            except Exception:
                return None

    elif isinstance(date_val, datetime):
        if date_val.tzinfo is None:
            if effective_tz is None:
                return None
            dt = date_val.replace(tzinfo=effective_tz)
        else:
            dt = date_val.astimezone(timezone.utc)

    if dt is not None:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return None
