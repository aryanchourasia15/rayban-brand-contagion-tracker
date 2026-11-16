"""Additive, append-only classification storage using the existing SQLite manager."""
import hashlib
import json

from src.data.db import get_connection, get_utc_now_iso, init_db
from src.analysis.schema import validate_labels


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def init_analysis_db(db_path=None):
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS classification_permissions (
                permission_id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT NOT NULL REFERENCES records(record_id),
                action TEXT NOT NULL CHECK(action IN ('grant','revoke')),
                scope TEXT NOT NULL, reference TEXT NOT NULL, verified_by TEXT NOT NULL,
                verified INTEGER NOT NULL CHECK(verified IN (0,1)), created_at TEXT NOT NULL
            )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS classification_attempts (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT NOT NULL REFERENCES records(record_id), input_hash TEXT NOT NULL,
                permission_id INTEGER REFERENCES classification_permissions(permission_id),
                method TEXT NOT NULL CHECK(method IN ('ollama','rule_based_test')),
                status TEXT NOT NULL CHECK(status IN ('success','failed')),
                labels_json TEXT, raw_output TEXT, error TEXT,
                model_name TEXT NOT NULL, model_version TEXT NOT NULL, runtime_version TEXT NOT NULL,
                prompt_version TEXT NOT NULL, is_synthetic INTEGER NOT NULL,
                needs_review INTEGER NOT NULL, created_at TEXT NOT NULL
            )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS human_reviews (
                review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER NOT NULL REFERENCES classification_attempts(attempt_id),
                reviewer TEXT NOT NULL, labels_json TEXT NOT NULL, rationale TEXT NOT NULL,
                created_at TEXT NOT NULL
            )''')
            for table, column in [('classification_permissions', 'record_id'),
                                  ('classification_attempts', 'record_id'), ('human_reviews', 'attempt_id')]:
                conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_parent ON {table}({column})')
                for operation in ('UPDATE', 'DELETE'):
                    conn.execute(f'''CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()}
                        BEFORE {operation} ON {table} BEGIN
                        SELECT RAISE(ABORT, 'Classification history is append-only'); END''')
    finally:
        conn.close()


def _permission(conn, record_id):
    row = conn.execute('SELECT * FROM classification_permissions WHERE record_id=? ORDER BY permission_id DESC LIMIT 1', (record_id,)).fetchone()
    if row and row['action'] == 'grant' and row['verified'] == 1 and row['scope'] == 'local_ai_analysis':
        return dict(row)
    return None


def record_permission(record_id, reference, verified_by, *, verified, revoke=False, db_path=None):
    """Record a human's verification of actual authorization, not an automatic grant.

    Covers local inference, human review and retention of resulting labels. No
    cloud transfer/model training rights are inferred. Revocation appends an event.
    """
    if type(verified) is not bool or not isinstance(reference, str) or not reference.strip() or not isinstance(verified_by, str) or not verified_by.strip():
        raise ValueError('A permission reference, verifier and explicit verification state are required.')
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute('''INSERT INTO classification_permissions
                (record_id,action,scope,reference,verified_by,verified,created_at)
                VALUES (?,?,?,?,?,?,?)''', (record_id, 'revoke' if revoke else 'grant',
                'local_ai_analysis', reference, verified_by, int(verified), get_utc_now_iso()))
            return cur.lastrowid
    finally:
        conn.close()


def load_eligible_record(record_id, db_path=None):
    conn = get_connection(db_path)
    try:
        with conn:
            record = conn.execute('SELECT * FROM records WHERE record_id=?', (record_id,)).fetchone()
            if not record:
                raise ValueError('Record not found.')
            record = dict(record)
            if record['source_type'] != 'customer_discussion' or record['status'] != 'valid':
                raise ValueError('Only valid customer discussions can be classified.')
            permission = _permission(conn, record_id)
            if not record['is_synthetic'] and not permission:
                raise PermissionError('Verified permission for local AI analysis is absent or revoked.')
            record['_permission_id'] = permission['permission_id'] if permission else None
            return record
    finally:
        conn.close()


def append_attempt(record, *, method, status, labels, raw_output, error, metadata,
                   prompt_version, needs_review, db_path=None):
    """Atomically recheck input/permission and append one attempt."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            current = conn.execute('SELECT * FROM records WHERE record_id=?', (record['record_id'],)).fetchone()
            if not current or text_hash(current['text']) != text_hash(record['text']) or current['is_synthetic'] != record['is_synthetic'] or current['source_type'] != 'customer_discussion' or current['status'] != 'valid':
                raise ValueError('Input changed during classification; retry after verification.')
            if method not in ('ollama', 'rule_based_test') or (method == 'rule_based_test' and not current['is_synthetic']):
                raise ValueError('Rule-based testing is restricted to synthetic records.')
            permission = _permission(conn, record['record_id'])
            if not current['is_synthetic'] and (not permission or permission['permission_id'] != record['_permission_id']):
                raise PermissionError('Permission changed during classification; output was not stored.')
            if status == 'success':
                labels = validate_labels(labels, record['text'])
            elif labels is not None:
                raise ValueError('Failed attempts cannot contain accepted labels.')
            cur = conn.execute('''INSERT INTO classification_attempts
                (record_id,input_hash,permission_id,method,status,labels_json,raw_output,error,
                 model_name,model_version,runtime_version,prompt_version,is_synthetic,needs_review,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                record['record_id'], text_hash(record['text']), record['_permission_id'], method, status,
                json.dumps(labels, ensure_ascii=False) if labels is not None else None, raw_output, error,
                metadata['model_name'], metadata['model_version'], metadata['runtime_version'],
                prompt_version, int(record['is_synthetic']), int(needs_review), get_utc_now_iso()))
            return cur.lastrowid
    finally:
        conn.close()


def append_review(attempt_id, labels, reviewer, rationale, db_path=None):
    if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(rationale, str) or not rationale.strip():
        raise ValueError('Reviewer and correction/confirmation rationale are required.')
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('''SELECT a.*,r.text,r.is_synthetic AS current_synthetic FROM classification_attempts a
                JOIN records r ON r.record_id=a.record_id WHERE a.attempt_id=?''', (attempt_id,)).fetchone()
            if not row or row['status'] != 'success' or text_hash(row['text']) != row['input_hash']:
                raise ValueError('Review requires a successful prediction on unchanged source text.')
            permission = _permission(conn, row['record_id'])
            if not row['is_synthetic'] and (not permission or permission['permission_id'] != row['permission_id']):
                raise PermissionError('Permission is absent, revoked or changed; reclassification is required.')
            validated = validate_labels(labels, row['text'])
            cur = conn.execute('INSERT INTO human_reviews (attempt_id,reviewer,labels_json,rationale,created_at) VALUES (?,?,?,?,?)',
                (attempt_id, reviewer, json.dumps(validated, ensure_ascii=False), rationale, get_utc_now_iso()))
            return cur.lastrowid
    finally:
        conn.close()


def get_history(record_id, db_path=None):
    conn = get_connection(db_path)
    try:
        attempts = [dict(row) for row in conn.execute('SELECT * FROM classification_attempts WHERE record_id=? ORDER BY attempt_id', (record_id,))]
        reviews = [dict(row) for row in conn.execute('''SELECT h.* FROM human_reviews h
            JOIN classification_attempts a ON a.attempt_id=h.attempt_id WHERE a.record_id=? ORDER BY h.review_id''', (record_id,))]
        return dict(attempts=attempts, reviews=reviews)
    finally:
        conn.close()


def research_predictions(db_path=None):
    """One latest successful AI prediction per real, currently authorized record.

    Newer failed runs do not erase earlier valid predictions. Human labels are
    supplied separately. Model/prompt versions stay attached to every row.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute('''SELECT a.*,r.text FROM classification_attempts a JOIN records r ON r.record_id=a.record_id
            WHERE a.status='success' AND a.method='ollama' AND a.is_synthetic=0 AND r.is_synthetic=0
            AND r.source_type='customer_discussion' AND r.status='valid'
            AND a.attempt_id=(SELECT MAX(b.attempt_id) FROM classification_attempts b
                WHERE b.record_id=a.record_id AND b.status='success' AND b.method='ollama')''').fetchall()
        result = []
        for row in rows:
            permission = _permission(conn, row['record_id'])
            if not permission or permission['permission_id'] != row['permission_id'] or text_hash(row['text']) != row['input_hash']:
                continue
            item = dict(row)
            item.pop('text')
            review = conn.execute('SELECT * FROM human_reviews WHERE attempt_id=? ORDER BY review_id DESC LIMIT 1', (row['attempt_id'],)).fetchone()
            item['prediction'] = json.loads(item.pop('labels_json'))
            item['human_labels'] = json.loads(review['labels_json']) if review else None
            item['review_id'] = review['review_id'] if review else None
            result.append(item)
        return result
    finally:
        conn.close()
