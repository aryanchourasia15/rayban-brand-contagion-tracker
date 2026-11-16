# Initial publication review

Review date: 16 November 2026. This records a local review, not publication.

## Publication scope

The initial commit contains source code, tests, documentation, blank CSV templates,
explicitly synthetic fixtures, and a summary of previously recorded synthetic local
AI benchmarks. The `.env.example` file is a blank configuration template, not a
credential file. The mock credential in `tests/test_guardian.py` is an invented test
value. No real research comments, permissions, consent documents, or raw model
outputs are included.

Cloud entry point: `cloud_app.py`. It calls `main(cloud=True)` and always selects
synthetic demo mode, even if `RAYBAN_APP_MODE=local` is present. No database access,
API credentials, live inference or model downloads are required for the demo.

## Exclusions and review findings

- `/data/` excludes the private dataset without hiding the required `src/data/`
  backend package. This fixes the previous unanchored `data/` ignore pattern.
- Environment files (except the blank example), virtual environments, secret/key
  files, SQLite databases and sidecars, private/research/consent/participant folders,
  exports, uploads and raw `benchmarks/` output are excluded.
- Arbitrary CSV/JSON and common dataset formats are ignored; only approved blank
  templates, synthetic fixture paths and the public summary are exceptions.
- Git ignore checks passed for 24 sensitive paths and 9 required publication paths.
- Publication candidates were checked for literal credentials, private keys,
  credential-bearing URLs, email addresses and personal filesystem paths. The only
  credential-assignment finding was the deliberate mocked Guardian test value.
- All four CSV templates have exactly one header row. Discussion fixtures are
  marked synthetic. The public benchmark is marked synthetic-only and contains no
  raw model-output fields.

Ignore rules cannot identify arbitrary personal information or protect commit
metadata. Review every future addition and use a privacy-appropriate Git author
identity. Review existing remote history before merging if the GitHub repository
is not empty. Public-code licensing is not specified by this project; no brand
endorsement or rights to third-party research data are implied.

No remote was configured and no push or deployment was performed during preparation.
A sandbox ownership mismatch was handled using command-scoped `safe.directory`
for this repository; global Git trust settings were not changed.

## Initial commit file manifest (71 files)

- `.env.example`
- `.gitignore`
- `.streamlit/config.toml`
- `PHASE2_SPEC.md`
- `PROJECT_CONTEXT.md`
- `README.md`
- `app.py`
- `cloud_app.py`
- `demo/benchmark_summary.json`
- `docs/PUBLICATION_REVIEW.md`
- `docs/RESEARCH_COLLECTION_GUIDE.md`
- `pages/1_Data_Collection_Centre.py`
- `pages/2_Brand_Contagion_Analysis.py`
- `requirements.txt`
- `scripts/audit_quality.py`
- `scripts/benchmark_contagion.py`
- `scripts/check_dataset_quality.py`
- `scripts/gdelt_quick_fetch.py`
- `src/__init__.py`
- `src/analysis/__init__.py`
- `src/analysis/engine.py`
- `src/analysis/evaluation.py`
- `src/analysis/ollama_client.py`
- `src/analysis/prompts/brand-contagion-1.0.0.txt`
- `src/analysis/prompts/brand-contagion-2.0.0.txt`
- `src/analysis/schema.py`
- `src/analysis/storage.py`
- `src/config.py`
- `src/data/__init__.py`
- `src/data/classifier.py`
- `src/data/cleaner.py`
- `src/data/connectors/__init__.py`
- `src/data/connectors/gdelt.py`
- `src/data/connectors/guardian.py`
- `src/data/db.py`
- `src/data/deduplicator.py`
- `src/data/importers/__init__.py`
- `src/data/importers/file_importer.py`
- `src/ui/__init__.py`
- `src/ui/collection.py`
- `src/ui/contagion.py`
- `src/ui/contagion_data.py`
- `src/ui/data_access.py`
- `src/ui/demo_benchmark.py`
- `src/ui/runtime.py`
- `templates/collection_log.csv`
- `templates/historical_news.csv`
- `templates/reddit_records.csv`
- `templates/youtube_comments.csv`
- `tests/__init__.py`
- `tests/contagion_support.py`
- `tests/fixtures/contagion_baseline_v1_summary.json`
- `tests/fixtures/contagion_heldout_20.json`
- `tests/fixtures/contagion_regression_20.json`
- `tests/fixtures/synthetic_contagion.json`
- `tests/fixtures/synthetic_records.json`
- `tests/test_classifier.py`
- `tests/test_cleaner.py`
- `tests/test_contagion_dashboard.py`
- `tests/test_contagion_engine.py`
- `tests/test_contagion_prompt_versions.py`
- `tests/test_contagion_schema.py`
- `tests/test_dataset_quality.py`
- `tests/test_db.py`
- `tests/test_deduplicator.py`
- `tests/test_deployment.py`
- `tests/test_file_importer.py`
- `tests/test_gdelt.py`
- `tests/test_guardian.py`
- `tests/test_ollama_local.py`
- `tests/test_ui_data_access.py`
