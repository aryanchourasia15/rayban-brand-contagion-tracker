"""Read-only CSV/JSON research preflight; no network calls or production writes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.db import init_db, insert_record
from src.data.deduplicator import DeduplicationEngine
from src.data.importers.file_importer import (
    parse_file_to_rows, detect_column_mapping, validate_and_transform_rows,
)


def check_dataset(file_path, db_path=None):
    """Inspect every row using importer validation and production dedup rules.

    An optional existing database is copied read-only into disposable storage.
    Original text is not included in the report. Issues do not delete any rows.
    """
    file_path = Path(file_path)
    content = file_path.read_bytes()
    fingerprint = hashlib.sha256(content).hexdigest()
    rows, headers = parse_file_to_rows(content, file_format=file_path.suffix.lstrip('.').lower())
    mapping = detect_column_mapping(headers)
    counts, results = Counter(), []
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory) / 'quality.db'
        init_db(scratch)
        conn = sqlite3.connect(scratch)
        conn.row_factory = sqlite3.Row
        try:
            if db_path is not None:
                target = Path(db_path).resolve()
                if not target.is_file():
                    raise ValueError(f'Database does not exist: {target}')
                existing = sqlite3.connect(target.as_uri() + '?mode=ro', uri=True)
                try:
                    existing.backup(conn)
                finally:
                    existing.close()
            engine = DeduplicationEngine(scratch)
            for index, row in enumerate(rows, 1):
                issues = []
                def value(field):
                    if not isinstance(row, dict):
                        return None
                    return row.get(mapping.get(field, field))

                if not value('url') or not str(value('url')).strip():
                    issues.append('missing_source_url')
                if not value('published_at') or not str(value('published_at')).strip():
                    issues.append('missing_publication_date')
                explicit_source = value('source')
                if (not explicit_source or not str(explicit_source).strip()) and not value('subreddit'):
                    issues.append('missing_source_identification')
                if not value('source_type'):
                    issues.append('missing_source_type')
                valid, invalid = validate_and_transform_rows([row], column_mapping=mapping)
                result = dict(row_number=index, issues=issues, validation_errors=[], source=None,
                              source_type=None, relevance_flag=None, duplicate=None)
                if invalid:
                    issues.append('invalid_row')
                    result['validation_errors'] = invalid[0]['errors']
                else:
                    record = valid[0]
                    record['record_id'] = f'quality_{fingerprint}_{index}'
                    duplicate, cleaned, info = engine.process_and_deduplicate_record(record, conn=conn)
                    result.update(source=cleaned['source'], source_type=cleaned['source_type'],
                                  relevance_flag=cleaned['relevance_flag'])
                    counts[f"relevance_{cleaned['relevance_flag']}"] += 1
                    if cleaned['relevance_flag'] == 'irrelevant':
                        issues.append('review_relevance')
                    if cleaned['published_at']:
                        published = datetime.fromisoformat(cleaned['published_at'].replace('Z', '+00:00'))
                        if not 2023 <= published.year <= 2026:
                            issues.append('outside_research_period')
                        if published > datetime.now(timezone.utc):
                            issues.append('future_publication_date')
                    origin = row.get('origin_platform', '')
                    if cleaned['source'] == 'Imported' and not str(origin).strip():
                        issues.append('missing_origin_platform')
                    if duplicate:
                        issues.append('duplicate')
                        result['duplicate'] = {'reason': info['match_reason'],
                                               'matched_record_id': info['matched_record_id']}
                    else:
                        insert_record(cleaned, conn=conn)
                counts.update(issues)
                results.append(result)
        finally:
            conn.close()
    return {'file': str(file_path), 'sha256': fingerprint,
            'database_checked': str(db_path) if db_path is not None else None,
            'total_rows': len(rows), 'rows_with_issues': sum(bool(row['issues']) for row in results),
            'counts': dict(sorted(counts.items())), 'rows': results,
            'notes': 'Relevance is heuristic triage, not sentiment. Duplicate matches include earlier file rows. No records were imported.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--database', type=Path, help='Existing SQLite database to check as well as within-file duplicates')
    args = parser.parse_args()
    try:
        report = check_dataset(args.file, args.database)
    except Exception as exc:
        parser.exit(2, f'Quality check failed: {exc}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if not report['total_rows'] or report['rows_with_issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
