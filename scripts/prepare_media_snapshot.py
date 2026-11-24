"""Export allowlisted existing media labels and review states; no collection or inference."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.simulation import fingerprint
from src.ui.media_evidence import DATA_DIR, load_media_rows
from src.ui.media_insights import KIND, RECORD_FIELDS, validate_snapshot
from src.ui.synthetic_reactions import load_public_sources


def prepare_snapshot():
    rows = load_media_rows()
    if rows is None:
        raise ValueError('The original local media corpus is required; no substitute coding is generated.')
    manifest = load_public_sources()
    records = [{key: row[key] for key in sorted(RECORD_FIELDS)} for row in rows]
    ledger = DATA_DIR/'media_review_events.csv'
    report = dict(kind=KIND, as_of='2026-11-24', source_csv_sha256=manifest['source_sha256'],
                  source_manifest_sha256=manifest['sha256'],
                  review_ledger_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest() if ledger.exists() else '',
                  records=records, records_sha256=fingerprint(records))
    validate_snapshot(report, manifest)
    target = ROOT/'demo/media_analysis.json'
    target.write_text(json.dumps(report, ensure_ascii=True, indent=2)+'\n', encoding='utf-8')
    print(f'Exported {len(records)} existing media coding records. No source text or reviewer identities exported.')


if __name__ == '__main__':
    prepare_snapshot()
