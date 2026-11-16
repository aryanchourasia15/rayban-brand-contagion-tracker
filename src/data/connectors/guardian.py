"""Guardian historical headline collection. Credentials never enter persisted payloads."""
from datetime import date, datetime, timezone
import hashlib
import os
import threading
import time

import requests

from src.config import GUARDIAN_ENABLED
from src.data.cleaner import canonicalize_url, parse_date_to_utc_iso
from src.data.db import start_batch, finish_batch, log_event, get_utc_now_iso
from src.data.deduplicator import DeduplicationEngine

BASE_URL = 'https://content.guardianapis.com/search'
_lock = threading.Lock()
_last_request = None
_daily_requests = {}


def _request(session, params, key):
    """Share one-request/second and 500/day budgets across this process's sessions."""
    global _last_request
    if not GUARDIAN_ENABLED:
        raise RuntimeError('Guardian collection is disabled pending licence clarification.')
    with _lock:
        today = datetime.now(timezone.utc).date().isoformat()
        budget = (today, hashlib.sha256(key.encode()).hexdigest())
        if _daily_requests.get(budget, 0) >= 500:
            raise RuntimeError('Guardian daily request budget reached; retry tomorrow.')
        if _last_request is not None:
            time.sleep(max(0, 1.05 - (time.monotonic() - _last_request)))
        _daily_requests[budget] = _daily_requests.get(budget, 0) + 1
        _last_request = time.monotonic()
        # Guardian's documented query authentication. Never print request URLs/errors.
        return session.get(BASE_URL, params={**params, 'api-key': key}, timeout=15,
                           headers={'User-Agent': 'RayBanTrustIntelligence/1.0 Academic Research'},
                           allow_redirects=False)


def transform_guardian_article_to_record(article, query, *, provenance=None):
    if not isinstance(article, dict):
        return None
    headline, article_id, url = (article.get(field) for field in ('webTitle', 'id', 'webUrl'))
    if not all(isinstance(value, str) and value.strip() for value in (headline, article_id, url)):
        return None
    canonical, domain = canonicalize_url(url)
    if not canonical or domain not in ('theguardian.com', 'theobserver.com') or not url.startswith(('https://', 'http://')):
        return None
    published = parse_date_to_utc_iso(article.get('webPublicationDate'), source='News')
    if not published:
        return None
    # Deliberately whitelist metadata even if the API unexpectedly sends full bodies.
    payload = {field: article[field] for field in ('id', 'type', 'sectionId', 'sectionName',
               'webTitle', 'webUrl', 'webPublicationDate', 'isHosted', 'pillarId', 'pillarName') if field in article}
    fields = article.get('fields')
    if isinstance(fields, dict):
        payload['fields'] = {name: fields[name] for name in ('byline', 'lastModified', 'publication') if name in fields}
    publisher = fields.get('publication') if isinstance(fields, dict) else None
    payload.update(provider='Guardian API', publisher=publisher or 'The Guardian', content_scope='headline_only',
                   search_query=query, **(provenance or {}))
    return dict(source='News', source_type='media', source_id=f'guardian:{article_id}',
                title=headline, text=headline, original_url=url, published_at=published,
                collection_method='Guardian API', raw_payload=payload)


def preview_guardian(query, start_date='2023-01-01', end_date=None, max_records=50,
                     start_page=1, session=None):
    """Fetch a bounded paginated snapshot, without writing to SQLite.

    Both the API key and a reference to applicable research permission are required.
    Returns sanitized errors: requests exceptions may contain credential-bearing URLs.
    """
    result = dict(success=False, query=query, preview_records=[], invalid_count=0,
                  total_found=0, pages_fetched=0)
    if not GUARDIAN_ENABLED:
        return {**result, 'error': 'Guardian collection is disabled pending licence clarification.'}
    key = os.getenv('GUARDIAN_API_KEY', '').strip()
    permission = os.getenv('GUARDIAN_PERMISSION_REFERENCE', '').strip()
    if not key:
        return {**result, 'error': 'Configure GUARDIAN_API_KEY in the server environment.'}
    if not permission:
        return {**result, 'error': 'Configure GUARDIAN_PERMISSION_REFERENCE for the approved research use and retention.'}
    try:
        start = date.fromisoformat(str(start_date))
        end = date.fromisoformat(str(end_date)) if end_date else datetime.now(timezone.utc).date()
        if not isinstance(query, str) or not query.strip():
            raise ValueError('Enter a nonempty search query.')
        if start > end:
            raise ValueError('Start date must not follow end date.')
        if not isinstance(max_records, int) or not 1 <= max_records <= 1000:
            raise ValueError('Maximum results must be between 1 and 1000.')
        if not isinstance(start_page, int) or start_page < 1:
            raise ValueError('Start page must be a positive integer.')
    except (ValueError, TypeError):
        return {**result, 'error': 'Use YYYY-MM-DD dates, start <= end, 1–1000 results and a positive start page.'}
    http = session or requests.Session()
    retrieved = get_utc_now_iso()
    processed = 0
    page = start_page
    page_size = min(50, max_records)
    try:
        while processed < max_records:
            params = {'q': query.strip(), 'from-date': start.isoformat(), 'to-date': end.isoformat(),
                      'page': page, 'page-size': page_size, 'order-by': 'oldest',
                      'show-fields': 'byline,lastModified,publication', 'tag': 'type/article'}
            for attempt in range(3):
                response = _request(http, params, key)
                if response.status_code not in (500, 502, 503, 504) or attempt == 2:
                    break
                time.sleep(2 ** attempt)
            if response.status_code in (401, 403):
                return {**result, 'error': 'Guardian authentication/access denied (HTTP 401/403). Check key and access scope.'}
            if response.status_code == 429:
                return {**result, 'error': 'Guardian rate limit or daily quota reached (HTTP 429). Stop and retry after the provider resets the limit.'}
            if response.status_code != 200:
                return {**result, 'error': f'Guardian request failed (HTTP {response.status_code}).'}
            data = response.json()
            data = data.get('response') if isinstance(data, dict) else None
            if not isinstance(data, dict) or data.get('status') != 'ok' or not isinstance(data.get('results'), list):
                raise ValueError('Malformed response')
            pages, current, total = int(data['pages']), int(data['currentPage']), int(data['total'])
            if current != page or pages < 0 or total < 0:
                raise ValueError('Invalid pagination')
            result['total_found'] = total
            result['pages_fetched'] += 1
            partial_page = len(data['results']) > max_records - processed
            for article in data['results'][:max_records - processed]:
                processed += 1
                record = transform_guardian_article_to_record(article, query, provenance={
                    'from_date': start.isoformat(), 'to_date': end.isoformat(), 'page': page,
                    'page_size': page_size, 'retrieved_at': retrieved, 'permission_reference': permission})
                if record and start.isoformat() <= record['published_at'][:10] <= end.isoformat():
                    result['preview_records'].append(record)
                else:
                    result['invalid_count'] += 1
            if not data['results'] or page >= pages:
                break
            if processed >= max_records:
                break
            page += 1
        return {**result, 'success': True, 'processed': processed,
                'next_page': page if partial_page else (page + 1 if page < pages else None),
                'partial_page': partial_page, 'page_size': page_size,
                'content_scope': 'headline_only'}
    except RuntimeError:
        return {**result, 'error': 'Guardian local daily request budget reached. Retry tomorrow.'}
    except (requests.RequestException, TimeoutError):
        return {**result, 'preview_records': [], 'error': 'Guardian connection failed or timed out. Retry later.'}
    except (ValueError, KeyError, TypeError):
        return {**result, 'preview_records': [], 'error': 'Guardian returned malformed metadata or pagination.'}
    finally:
        if session is None:
            http.close()


def import_guardian_preview(preview, db_path=None):
    """Persist only a successful, explicitly confirmed snapshot; never refetch."""
    if not GUARDIAN_ENABLED:
        raise ValueError('Guardian imports are disabled pending licence clarification.')
    if not preview.get('success') or not preview.get('preview_records'):
        raise ValueError('A successful nonempty Guardian preview is required.')
    permission = os.getenv('GUARDIAN_PERMISSION_REFERENCE', '').strip()
    if not permission:
        raise ValueError('Research permission reference is required before import.')
    records = []
    for record in preview['preview_records']:
        payload = record.get('raw_payload', {})
        clean = transform_guardian_article_to_record(payload, preview['query'], provenance={
            field: payload[field] for field in ('from_date', 'to_date', 'page', 'page_size',
                                               'retrieved_at', 'permission_reference') if field in payload})
        if not clean or payload.get('permission_reference') != permission:
            raise ValueError('Preview provenance or permission changed; search again.')
        records.append(clean)
    batch = start_batch('News', 'Guardian API', batch_name='Guardian historical headlines', db_path=db_path)
    invalid = preview.get('invalid_count', 0)
    try:
        result = DeduplicationEngine(db_path).ingest_batch_safely(records, batch_id=batch)
    except Exception:
        finish_batch(batch, status='failed', error_details='Guardian preview ingestion failed.', db_path=db_path)
        log_event(batch, 'ERROR', 'Guardian preview ingestion failed.', db_path=db_path)
        raise RuntimeError('Guardian preview ingestion failed; inspect the database configuration.') from None
    finish_batch(batch, status='partial' if invalid else 'completed', processed=len(records) + invalid,
                 imported=result['imported'], duplicate=result['duplicate'], invalid=invalid, db_path=db_path)
    log_event(batch, 'INFO', 'Imported confirmed Guardian headline-only preview.', db_path=db_path)
    return dict(batch_id=batch, imported=result['imported'], duplicates=result['duplicate'], invalid=invalid)
