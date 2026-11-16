"""
Unit tests for Module 2: Data Cleaning, Normalization, URL Canonicalization, and Date Parsing.
"""

import unittest

from src.data.cleaner import (
    canonicalize_url,
    compute_content_hash,
    is_generic_or_too_short,
    normalize_text,
    parse_date_to_utc_iso,
)


class TestCleanerModule(unittest.TestCase):
    def test_normalize_entities_and_controls(self):
        self.assertEqual(
            normalize_text('  Trust&nbsp;&amp; &#8220;Privacy&#8221;\x00\u200b\u202e\x7f\nNext\tLine  '),
            'trust & "privacy" next line',
        )

    def test_normalize_text_unicode_quotes_and_whitespace(self):
        """Test Unicode NFKC normalization, smart quotes replacement, whitespace collapse, and lowercasing."""
        raw = "  “Smart glasses”   by   Ray-Ban & Meta…\n\nAre they   safe?  "
        normalized = normalize_text(raw)
        self.assertEqual(normalized, '"smart glasses" by ray-ban & meta... are they safe?')

        # Preserves original raw text completely (tested by caller retaining raw)
        self.assertNotEqual(raw, normalized)

    def test_normalize_text_none_and_empty(self):
        """Test safe handling of None and empty strings."""
        self.assertEqual(normalize_text(None), "")
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text("   "), "")

    def test_compute_content_hash_deterministic(self):
        """Test that compute_content_hash produces deterministic SHA-256 hex strings."""
        norm1 = normalize_text("Privacy in public spaces with Ray-Ban Meta")
        norm2 = normalize_text("Privacy in public spaces with Ray-Ban Meta")
        hash1 = compute_content_hash(norm1)
        hash2 = compute_content_hash(norm2)

        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)

        # Different text produces different hash
        hash3 = compute_content_hash(normalize_text("Different comment text"))
        self.assertNotEqual(hash1, hash3)

    def test_is_generic_or_too_short(self):
        """Test detection of generic and short comments to prevent false positive deduplication."""
        # Generic phrases
        self.assertTrue(is_generic_or_too_short("agree"))
        self.assertTrue(is_generic_or_too_short("cool"))
        self.assertTrue(is_generic_or_too_short("thanks"))
        self.assertTrue(is_generic_or_too_short("[deleted]"))
        self.assertTrue(is_generic_or_too_short("[removed]"))
        self.assertTrue(is_generic_or_too_short("yes"))

        # Too short (< 50 chars or < 8 words)
        self.assertTrue(is_generic_or_too_short("I agree completely"))
        self.assertTrue(is_generic_or_too_short("Not good"))

        # Substantial comment (>= 50 chars and >= 8 words)
        substantial = "i am concerned about the hidden camera recording people without consent"
        self.assertFalse(is_generic_or_too_short(substantial))

    def test_canonicalize_url_clean_and_params(self):
        """Test URL canonicalization: scheme, lowercase domain, www strip, tracking param removal, fragment strip."""
        url = "HTTP://WWW.THEVERGE.COM/2024/3/1/glasses-privacy/?utm_source=twitter&utm_medium=social&articleId=456#comments"
        canonical, domain = canonicalize_url(url)

        self.assertEqual(domain, "theverge.com")
        self.assertEqual(canonical, "http://theverge.com/2024/3/1/glasses-privacy?articleId=456")
        self.assertNotIn("utm_source", canonical)
        self.assertNotIn("#comments", canonical)

    def test_canonicalize_url_default_ports_and_trailing_slash(self):
        """Test standard port removal and trailing slash normalization."""
        url1 = "https://reddit.com:443/r/privacy/comments/123/"
        canonical1, domain1 = canonicalize_url(url1)
        self.assertEqual(canonical1, "https://reddit.com/r/privacy/comments/123")
        self.assertEqual(domain1, "reddit.com")

        # Missing scheme adds https://
        url2 = "techcrunch.com/article/meta-rayban"
        canonical2, domain2 = canonicalize_url(url2)
        self.assertEqual(canonical2, "https://techcrunch.com/article/meta-rayban")
        self.assertEqual(domain2, "techcrunch.com")

    def test_canonicalize_url_malformed(self):
        """Test safe handling of malformed or invalid URLs."""
        self.assertEqual(canonicalize_url(None), (None, None))
        self.assertEqual(canonicalize_url(""), (None, None))
        self.assertEqual(canonicalize_url("   "), (None, None))
        self.assertEqual(canonicalize_url("not a url at all :::"), (None, None))

    def test_parse_date_to_utc_iso_unambiguous_formats(self):
        """Test date parsing for unambiguous formats: ISO-8601 with offset, named months, and Unix timestamps."""
        # ISO-8601 with explicit offset
        self.assertEqual(
            parse_date_to_utc_iso("2024-03-15T16:30:00+02:00"),
            "2024-03-15T14:30:00Z",
        )

        # ISO-8601 UTC Z indicator
        self.assertEqual(
            parse_date_to_utc_iso("2024-03-15T14:30:00Z"),
            "2024-03-15T14:30:00Z",
        )

        # Unix timestamp in seconds (always UTC)
        self.assertEqual(
            parse_date_to_utc_iso(1710513000),
            "2024-03-15T14:30:00Z",
        )

        # Unix timestamp in milliseconds
        self.assertEqual(
            parse_date_to_utc_iso(1710513000000),
            "2024-03-15T14:30:00Z",
        )

    def test_parse_date_to_utc_iso_explicit_ambiguity_handling(self):
        """Test that ambiguous day/month or naive timezones are handled explicitly and never silently guessed."""
        from datetime import timezone

        # 1. Ambiguous day/month (03/04/2024): rejected when day_first is None
        self.assertIsNone(parse_date_to_utc_iso("03/04/2024"))

        # Explicit day_first=True
        self.assertEqual(
            parse_date_to_utc_iso("03/04/2024", day_first=True, default_tz=timezone.utc),
            "2024-04-03T00:00:00Z",
        )

        # Explicit day_first=False
        self.assertEqual(
            parse_date_to_utc_iso("03/04/2024", day_first=False, default_tz=timezone.utc),
            "2024-03-04T00:00:00Z",
        )

        # 2. Naive datetime strings without timezone: rejected without documented rule or default_tz
        self.assertIsNone(parse_date_to_utc_iso("2024-03-15 14:30:00"))

        # Resolved with documented source rule (Reddit API timestamps are UTC)
        self.assertEqual(
            parse_date_to_utc_iso("2024-03-15 14:30:00", source="Reddit"),
            "2024-03-15T14:30:00Z",
        )

        # Resolved with explicit default_tz
        self.assertEqual(
            parse_date_to_utc_iso("2024-03-15 14:30:00", default_tz=timezone.utc),
            "2024-03-15T14:30:00Z",
        )

    def test_parse_date_to_utc_iso_never_invents_missing_dates(self):
        """Never invent missing or unparseable dates; return None."""
        self.assertIsNone(parse_date_to_utc_iso(None))
        self.assertIsNone(parse_date_to_utc_iso(""))
        self.assertIsNone(parse_date_to_utc_iso("   "))
        self.assertIsNone(parse_date_to_utc_iso("null"))
        self.assertIsNone(parse_date_to_utc_iso("invalid date text"))


if __name__ == "__main__":
    unittest.main()
