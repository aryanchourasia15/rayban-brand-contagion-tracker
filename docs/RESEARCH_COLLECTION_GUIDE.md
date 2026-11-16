# Research collection protocol: 2023–2026

Policy/access sources checked 15 November 2026. Recheck before each collection.
This is a collection protocol, not a claim that any platform has approved this project.
No real comments have been collected or imported by this implementation.

## Scope and sampling

Test H1, H2 and H3 from PROJECT_CONTEXT.md without presuming brand damage.
Prioritize genuine public discussions; ownership is self-reported, not verified.
Keep media in a separate stratum. Do not treat a journalist's wording as a customer's opinion.
Cover 1 January 2023 through the actual collection cutoff in 2026, never future dates.
Record gaps explicitly; an empty or unavailable year is not evidence of no concern.

Before collecting, fix a sampling rule in `templates/collection_log.csv`:
platform × year/quarter × language × query family. Use both neutral product searches
(`"Ray-Ban Meta"`, `"Ray-Ban Stories"`, `"Ray-Ban" eyewear`, `"Meta smart glasses"`)
and concern searches (privacy, recording, consent, surveillance). Include positive,
neutral and product/fashion-only discussions as comparators. Add French queries
such as `"lunettes Meta" vie privée` only if language coverage is planned.
Record sorting, parent selection, a fixed cap per parent, reply inclusion rule,
pagination stopping rule and exclusions before inspecting opinions. Popularity-ranked
convenience samples and missing/deleted comments create selection bias.

Use ordinary search interfaces to discover candidate pages. Log exact queries,
dates, sorting and candidate URLs, including zero results. Discovery does not grant
permission to export or redistribute text. Never bypass logins, CAPTCHAs, paywalls,
API denials, private communities or disabled comments. Do not use third-party scraped
archives as a substitute for authorization.

## Sources and permitted routes

### Reddit: prioritize the approved academic route

[Reddit for Researchers](https://support.reddithelp.com/hc/en-us/articles/49381918834964-Reddit-for-Researchers-Program)
offers free non-commercial academic access via BigQuery Analytics Hub. Apply using
HEC credentials with a faculty sponsor and ethics approval/exemption. Current coverage
is five years with a six-month delay, so late-2026 evidence will be incomplete.
Offline copies must be necessary for the immediate research; sharing and retention
are restricted. Confirm that local CSV/SQLite use is permitted by the signed terms.
Recheck deleted content before publication. Credentials alone do not authorize collection.

Candidate communities to investigate, subject to availability and approved scope:
r/RayBanStories, r/RayBan, r/privacy and r/technology. Verify each community rather
than assuming it is active or contains relevant evidence. Use approved queries/exports;
record subreddit, post and parent IDs. While approval is pending, build a URL-only
candidate register rather than bulk-copying discussion text. Do not assume manual
copying creates an exception to platform or institutional requirements.

### YouTube: public comment API with conditions

Discover owner reviews, long-term usage videos, fashion reviews and privacy coverage
through YouTube search, recording video URLs and publication dates. A video is a
sampling container: each comment has its own date and is a separate evidence unit.
Never assume a commenter is a purchaser.

The [Data API overview](https://developers.google.com/youtube/v3/getting-started)
explains project/API-key setup and default quota. Stay within the provided quota;
do not rotate projects or purchase access. With an eligible project, use
[`commentThreads.list`](https://developers.google.com/youtube/v3/docs/commentThreads/list)
with `part=snippet`, `videoId`, `maxResults=100`, `order=time`, `textFormat=plainText`;
follow `nextPageToken`. For replies, paginate
[`comments.list`](https://developers.google.com/youtube/v3/docs/comments/list)
using `parentId`. Do not equate embedded replies with a complete thread. Filter by
each comment's `publishedAt` locally; these listing methods do not accept a comment
publication-date range. Stop on quota/permission errors and record the coverage gap.

The [comment resource](https://developers.google.com/youtube/v3/docs/comments)
provides `id`, `publishedAt`, `updatedAt` and text. Preserve returned text exactly.
Public `textDisplay` can differ from author-original text; `textOriginal` is restricted
to the authenticated author. Record `text_representation=textDisplay_plainText`
when applicable, rather than claiming access to the original author string.

The [developer policies](https://developers.google.com/youtube/terms/developer-policies)
restrict derived data/metrics and require refresh or deletion of most stored public
API data within 30 days. The current dashboard automatically derives relevance flags
and has no retention/deletion scheduler. Therefore ordinary API access alone is not
confirmation that this research/dashboard use is permitted. Seek a documented route
covering these uses, for example via the [researcher programme](https://research.youtube/).
Do not import YouTube comments until scope and retention handling are resolved.
Apply deletion/refresh obligations to CSVs, SQLite, raw payloads, reports and backups;
an idempotent re-import does not refresh an existing record. Do not scrape the website
or use a downloader to evade these conditions.

### Historical news: start with the Guardian and publisher archives

**Update, 16 November 2026: Guardian collection is blocked pending licence clarification.**
Do not use a standard developer key for this research dataset. The connector's
default-off block applies even when credentials or a permission reference exist.
The historical route described below is conditional on explicit authorization
covering analysis and retention; it is not an instruction to collect now.

The [Guardian developer tier](https://open-platform.theguardian.com/access/)
is free for non-commercial uses including student dissertations: currently 500 calls
per day, one per second. Register a key, review its terms and use the
[Content API documentation](https://open-platform.theguardian.com/documentation/).
Search Ray-Ban Meta/Stories across the target years; map `webTitle` to `title`,
`webUrl` to `url`, `webPublicationDate` to `published_at`, and namespace its `id`.
For a minimal metadata dataset set `text` to the exact headline and
`content_scope=headline_only`; do not describe it as full article evidence.

Publisher search/archive pages and ordinary search date filters provide additional
candidate URLs. Open the original article to verify its publication date, title and
publisher. Retain only text allowed by the publisher's terms or explicit permission;
free reading is not a general full-text redistribution licence. Keep original and
update dates separate; do not use search-result dates as verified publication dates.

[GDELT raw datasets](https://www.gdeltproject.org/data.html) are a free historical
discovery option, but date-partitioned GKG/event files require separate filtering.
They are not CSVs ready for this importer and contain discovery/event timestamps,
which must not be substituted for publication dates. Use resulting URLs to verify
publisher metadata. Avoid billable BigQuery jobs under this no-paid-services brief.
The existing dashboard's GDELT connector enforces ~90 days; keep it for recent
coverage and import historical evidence through files. Do not assume old DOC API
announcements guarantee present endpoint coverage or complete 2023–2026 retrieval.

## Template fields and provenance

The three source templates contain headers only: no invented comments or articles.
Use one row per post, comment or article and preserve line breaks with proper CSV
quoting. Use UTF-8; do not edit spelling, translate, trim or summarize `text`.
Keep any separate permitted translation outside the original field.

| Field | Collection rule |
| --- | --- |
| `text` | Exact permitted source representation; headlines are acceptable only when labelled as such. |
| `title` | Post/video/article title for context; a parent's wording does not prove a comment expresses the same view. |
| `published_at` | Verified original ISO-8601 timestamp with explicit UTC/offset; never the retrieval or edit date. |
| `url` | Direct item permalink, not a search page or shared parent URL for every comment. |
| `source`, `source_type` | Reddit: `Reddit`, `customer_discussion`; YouTube: `Imported`, `customer_discussion`; news: `News`, `media`. |
| `source_id` | Stable namespaced ID: Reddit fullname (`t1_` comment / `t3_` post); YouTube `youtube:COMMENT_ID`; news `guardian:CONTENT_ID` or publisher URL. |
| `origin_platform` | `Reddit`, `YouTube`, or the actual news provider/archive. Do not use `source=YouTube`, which the schema does not support. |
| `retrieved_at` | Actual collection time, distinct from the database's import-time `collected_at`. |
| `publication_date_raw`, `date_precision` | Preserve source date representation and precision; for a date-only source, document a UTC-midnight analytical convention and `date_precision=day`. If unknown, leave blank and quarantine. |
| `collection_run_id`, `search_query`, `selection_reason` | Link every row to the collection log and predeclared selection rule. |
| `access_basis`, `permission_reference`, `retention_review_at` | Actual authorization/terms reference and retention review deadline; do not invent approval. |
| `manual_relevance`, `exclusion_reason` | Human screening rationale; review relevance separately from sentiment or spillover. |

Reddit: use the full permalink including the specific comment segment. YouTube:
use `https://www.youtube.com/watch?v=VIDEO_ID&lc=COMMENT_ID`, verifying the link where
available. The `lc` parameter is essential: a shared video URL deduplicates distinct
comments. Preserve `parent_id` and `video_id`/`post_id` to reconstruct context.
Do not collect author names, profiles or sensitive personal details unless separately
necessary and authorized. Put restricted exports outside version control and restrict
dashboard access; do not publish raw customer CSVs.

The importer preserves all original columns in `raw_payload`. Additional collection
fields, including `retrieved_at`, `manual_relevance` and retention information, remain
there; they do not override database timestamps or automated relevance flags.
All file imports use `collection_method=CSV import`, including authorized API exports.

## Preflight and dashboard import

1. Copy a source template to a restricted working folder; populate only genuine,
   permitted records. Keep a collection log even for unsuccessful searches. For each
   year, first run a small pilot using the same selection rule; never fill missing
   cells with invented data or a guessed date.
2. From the project directory run:

   ```powershell
   .venv\Scripts\python scripts/check_dataset_quality.py path\to\collected.csv --database data\database\trust_intelligence.db
   ```

   Omit `--database` for within-file checks only. JSON is also supported. The report
   goes to stdout; save it privately if needed. Exit 0 = nonempty with no flags;
   1 = review issues or empty file; 2 = unable to check. The SHA-256 fingerprint
   links the report to its exact input. No file rows or database records are changed.
3. Resolve missing URLs/dates/source identification and validation errors against
   the original evidence. The backend accepts absent URL/date fields, so this
   preflight is stricter. Do not import unresolved rows into the dated research sample.
4. Review duplicate reasons (`source_id`, `canonical_url`, `content_hash`) against
   earlier rows and the database snapshot. The checker uses the existing engine,
   including protections for short comments and different-publisher headlines.
   It is exact matching, not fuzzy or semantic duplicate detection.
5. Inspect heuristic `relevant`, `contextual`, `irrelevant` flags manually. Product
   context can make a short reply relevant even without keywords; parent titles can
   also cause false positives. Never automatically delete an irrelevant flag or
   interpret it as sentiment. Keep screening decisions and exclusions in the log.
6. Launch `.venv\Scripts\python -m streamlit run app.py`. In **CSV / JSON import**,
   upload the checked file, review mappings and the correct source/type, set date
   order/timezone explicitly, then **Validate & preview file**. Inspect errors and
   confirm **Import reviewed file**. A preview is not an import.
7. Check counts in Overview, inspect original records and distinct evidence types
   in Dataset explorer, and record the batch ID from Import history alongside the
   input fingerprint. Re-run the checker after changes. Re-importing detects exact
   duplicates but does not update or delete earlier records.

The checker does not certify permissions, customer identity, completeness, public URL
availability, timestamp precision or representativeness. It performs no network calls.
Keep permitted source exports unchanged for the authorized retention period, with
matching collection logs; honor deletion obligations over permanent reproducibility.
Report sample size, date/platform/language coverage and missingness alongside findings.
