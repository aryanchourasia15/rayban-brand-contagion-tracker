# Phase 2 Specification — Data Collection Centre

## 1. Objective
Build a robust, verifiable **Data Collection Centre** inside the Streamlit application for the **Ray-Ban Customer Trust Intelligence** platform.

The pipeline stages:
`Reddit / News / CSV or JSON → Ingestion → Validation → Cleaning → Deduplication → SQLite → Dataset Explorer`

---

## 2. Unified Database Schema (`trust_intelligence.db`)

### `records` table
- `record_id` (TEXT PRIMARY KEY): UUID or deterministic ID
- `source` (TEXT): `'Reddit'`, `'News'`, or `'Imported'`
- `source_type` (TEXT): `'customer_discussion'` or `'media'`
- `source_id` (TEXT): Platform ID (e.g., Reddit submission/comment ID)
- `title` (TEXT): Post title or article headline
- `text` (TEXT): Original unmodified text (never overwritten)
- `normalized_text` (TEXT): Cleaned/standardized text for hashing & matching
- `url` (TEXT): Canonical source URL
- `published_at` (TEXT ISO-8601 UTC): Original publication date/time
- `collected_at` (TEXT ISO-8601 UTC): Timestamp of ingestion
- `domain` (TEXT): Domain name (e.g. reddit.com, theverge.com)
- `collection_method` (TEXT): `'API'`, `'GDELT'`, or `'CSV import'`
- `content_hash` (TEXT): SHA-256 hash of normalized text
- `import_batch_id` (TEXT): Foreign key / reference to `import_batches`
- `status` (TEXT): `'valid'`, `'duplicate'`, `'invalid'`, or `'pending'`
- `raw_payload` (TEXT JSON): Original unmapped columns or raw API payload
- `created_at` (TEXT ISO-8601 UTC): DB insertion timestamp

**Indexes**:
- `idx_records_published_at` ON `records(published_at)`
- `idx_records_source` ON `records(source)`
- `idx_records_source_type` ON `records(source_type)`
- `idx_records_content_hash` ON `records(content_hash)`
- `idx_records_batch_id` ON `records(import_batch_id)`
- `idx_records_url` ON `records(url)`

### `import_batches` table
- `batch_id` (TEXT PRIMARY KEY)
- `source` (TEXT)
- `collection_method` (TEXT)
- `status` (TEXT)
- `records_processed` (INTEGER)
- `records_imported` (INTEGER)
- `records_duplicate` (INTEGER)
- `records_invalid` (INTEGER)
- `error_details` (TEXT)
- `created_at` (TEXT ISO-8601 UTC)

### `collection_logs` table
- `log_id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `batch_id` (TEXT)
- `level` (TEXT): `'INFO'`, `'WARNING'`, `'ERROR'`
- `message` (TEXT)
- `created_at` (TEXT ISO-8601 UTC)

---

## 3. Core Modules & Responsibilities

1. **Storage (`src/data/db.py`)**:
   - SQLite connection manager with WAL mode for concurrency.
   - Schema creation and migration idempotency.
   - Batch insertion transactions.

2. **Data Cleaning & Normalization (`src/data/cleaner.py`)**:
   - Whitespace trimming, unescaping, control character removal.
   - URL canonicalization (strip tracking query params `utm_*`, normalize scheme/host, trailing slash).
   - Domain extraction.
   - ISO-8601 UTC date parsing with fallback to fuzzy parsing (`dateutil.parser`).
   - Content hash generation (`SHA-256(normalized_text)`).

3. **Deduplication Engine (`src/data/deduplicator.py`)**:
   - Order of priority:
     1. Match `source_id` within the same source platform.
     2. Match canonical `url`.
     3. Match `content_hash` within the same `source_type`.
   - Logging of duplicate events and batch idempotency.

4. **CSV / JSON Ingestion (`src/data/importers/file_importer.py`)**:
   - Automatic column detection with aliases (`body`, `comment`, `content`, `text`, `headline`, `created`, `permalink`, etc.).
   - UI preview of first 10 rows + manual mapping overrides.
   - Validation against empty text, unparseable dates, malformed URLs.
   - Storage of unused columns into `raw_payload`.
   - Template CSV generation.

5. **GDELT News Ingestion (`src/data/connectors/gdelt.py`)**:
   - GDELT DOC 2.0 API (`ArticleList` endpoint, JSON mode).
   - Pre-configured queries:
     1. `"Ray-Ban Meta"`
     2. `"Ray-Ban" AND privacy`
     3. `"Meta smart glasses" AND recording`
     4. `"smart glasses" AND privacy`
     5. `"Ray-Ban Meta" AND workers`
     6. `"smart glasses" AND surveillance`
   - Configurable date range, max records, rate limiting, and backoff retries.
   - Rolling ~3-month caveat explicitly documented in UI.

6. **Reddit Connector (`src/data/connectors/reddit.py`)**:
   - Authorised credentials via `.env` (`REDRAWN_REDDIT_CLIENT_ID`, `CLIENT_SECRET`, `USER_AGENT`).
   - Status gating: if unconfigured or unauthorized, displays clear guidance without scraping or breaking.
   - Subreddit and keyword queries, rate limit compliance.

7. **Streamlit UI (`app.py` & `pages/1_Data_Collection_Centre.py`)**:
   - Overview metrics (Total records, customer vs. media counts, duplicates, batch status).
   - Tabbed or modular sections:
     - Tab A: Overview & Health
     - Tab B: CSV / JSON Ingestion & Template
     - Tab C: News (GDELT)
     - Tab D: Reddit (Authorised / Gated)
     - Tab E: Import History & Audit Logs
     - Tab F: Dataset Explorer (Filters, Text Search, Clickable Links, CSV Export)
