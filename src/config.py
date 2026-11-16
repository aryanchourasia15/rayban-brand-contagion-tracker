"""
Ray-Ban Customer Trust Intelligence
Configuration and Constants
"""

import os
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_DIR = DATA_DIR / "database"
DB_PATH = DATABASE_DIR / "trust_intelligence.db"

# Directories are created by db.get_connection only when storage is actually used.
# Importing configuration must not require a writable filesystem in public demo mode.

# Provenance Constraints & Schema Vocabularies
VALID_SOURCES = ("Reddit", "News", "Imported")
VALID_SOURCE_TYPES = ("customer_discussion", "media")
VALID_COLLECTION_METHODS = ("API", "GDELT", "Guardian API", "CSV import")
VALID_RECORD_STATUSES = ("valid", "duplicate", "invalid", "pending")
VALID_BATCH_STATUSES = ("started", "completed", "failed", "partial")
VALID_RELEVANCE_FLAGS = ("relevant", "contextual", "irrelevant")

# Deduplication Match Reasons
MATCH_REASONS = ("source_id", "canonical_url", "content_hash")

# GDELT Ingestion Settings
GDELT_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
DEFAULT_GDELT_QUERIES = [
    '"Ray-Ban Meta"',
    '"Ray-Ban" AND privacy',
    '"Meta smart glasses" AND recording',
    '"smart glasses" AND privacy',
    '"Ray-Ban Meta" AND workers',
    '"smart glasses" AND surveillance',
]
GDELT_DEFAULT_MAX_RECORDS = 100
GDELT_REQUEST_TIMEOUT_SECONDS = 15
GDELT_HISTORICAL_WINDOW_DAYS = 90  # Documentation constraint: GDELT rolling ~3 month window

# Guardian historical news searches
GUARDIAN_ENABLED = False  # Blocked pending licence clarification; credentials do not enable it.
DEFAULT_GUARDIAN_QUERIES = [
    '"Ray-Ban Meta"', '"Ray-Ban Stories"', '"Meta smart glasses"', '"Ray-Ban" privacy',
]

# Reddit Integration Settings
# Strictly disabled by default until authorized API credentials are explicitly configured.
REDDIT_ENABLED = False
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "RayBanTrustIntelligence/1.0")

if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
    REDDIT_ENABLED = True
