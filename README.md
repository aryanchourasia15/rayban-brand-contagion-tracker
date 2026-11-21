# Ray-Ban Customer Trust Intelligence

HEC Paris Strategic Management research artefact. The Data Collection Centre
keeps customer discussions separate from journalistic media evidence. Relevance is
a keyword-based triage flag, not a sentiment or brand-spillover conclusion.

The current approved demonstration uses locally AI-generated reactions
grounded in 32 genuine media references. All simulated charts are illustrative,
not empirical customer sentiment. The public `cloud_app.py` runs from curated
`demo/` artefacts without Ollama, credentials or private research files. Scenario
design labels and actual classifier outputs are shown separately. See
[the synthetic methodology](docs/SYNTHETIC_DEMONSTRATION.md) for generation,
reproduction, provenance and evaluation limitations. Nothing is published automatically.

The public view introduces the shareholder dilemma, then separates Strategic Question,
Evidence & Methodology, Brand Contagion Analysis, Strategic Recommendations and Research
Appendix. It retains 260 simulations, 32 contextual news sources, 220 historically
accepted predictions and 40 rejections. Reaction A/B/C describe customer mechanisms,
not measured shareholder outcomes. Legacy fixtures remain in the appendix.
[The 50-case error review](docs/CLASSIFICATION_ERROR_REVIEW.md) provides separate
AI-assisted proposals, never human-validation labels or replacements for saved
predictions. Historical prompt versions, benchmarks and the 260-case inputs remain
unchanged. Evidence rule `context-evidence-2.0` is opt-in; historical replay defaults
to `legacy-1.0`. Presentation release marker: `hec-copy-2026-11-21-v3`.

## Run locally (Python 3.11+)

From this directory, in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:RAYBAN_APP_MODE = "local"
.venv\Scripts\python -m streamlit run app.py --server.address 127.0.0.1
```

Open the local URL printed by Streamlit, normally http://localhost:8501.
SQLite is initialized automatically at `data/database/trust_intelligence.db`.
No database reads are cached; refresh the page or use **Refresh dataset** to see
changes made in another session. Imports run only on explicit confirmation.

## Public synthetic demo and Community Cloud deployment

The default `app.py` mode is **demo**. Research tools require an explicit
`RAYBAN_APP_MODE=local` environment variable. Invalid values stop startup.
For public hosting, always use **`cloud_app.py`**, which forces demo mode even
if that variable is accidentally set to `local`. No automatic hosting detection,
API credentials or Streamlit secrets are needed. A `.env` file is not loaded.

| Capability | Local research mode | Public/cloud demo |
| --- | --- | --- |
| SQLite, imports, research explorer | Available locally | Unavailable; no database reads/writes |
| Ollama | Installed loopback-only model, explicit permission checks | No connection or inference |
| Examples and analytics | Verified research or separately selected demo | Explicitly synthetic fixtures only |
| Benchmark | Previously recorded synthetic local runs | Same static, reviewed summary; no fresh inference |
| Human demo corrections | Session only | Session only; lost on session reset |

Test the exact cloud entry point locally:

```powershell
.venv\Scripts\python -m streamlit run cloud_app.py --server.address 127.0.0.1
.venv\Scripts\python -m unittest discover -v
```

The synthetic examples are curated reference labels, not AI predictions. Recorded
benchmark scores are displayed separately and include small-sample warnings,
safeguard acceptance counts and provenance. Synthetic records have no invented
publication dates or source URLs. Demo corrections and sessions never enter SQLite.
No persistent filesystem storage is needed for demo results. Restarting or sleeping
the hosted app may reset sessions. No research credentials should be configured.

### GitHub setup — execute only when publication is approved

This working directory was not a Git repository at the deployment audit. Create a
new, empty GitHub repository under your account (without an initial README), then
run these commands from the RayBan directory. Replace the remote placeholders.

```powershell
git init -b main
git add .gitignore .streamlit/config.toml requirements.txt app.py cloud_app.py README.md PROJECT_CONTEXT.md PHASE2_SPEC.md src pages templates tests scripts demo/benchmark_summary.json demo/research_timeline.json demo/case_study_results.json docs/RESEARCH_COLLECTION_GUIDE.md docs/CONTROVERSY_TIMELINE.md docs/AI_EVALUATION_SUMMARY.md docs/STRATEGIC_IMPLICATIONS.md docs/PUBLICATION_REVIEW.md
git diff --cached --name-only
git diff --cached
# STOP and review the staged files before the following publication commands.
git commit -m "Prepare synthetic Streamlit group demonstration"
git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
git push -u origin main
```

Publish application code, blank templates, labelled synthetic fixtures, reviewed
public demo JSON assets and original sourced paraphrases only. The ignore rules exclude environments,
secrets, databases, raw benchmarks, data, exports, uploads and common consent/private
folders. Arbitrary CSV/JSON files are ignored except approved fixture/template paths.
Do not use force-add. Ignore rules do not remove previously tracked files or Git
history: if reusing a repository, check `git ls-files` and its entire history first.
Do not upload comments, consent forms, personal information or credentials anywhere
in the public repository. New private filenames outside these patterns still require
manual review. The `.env.example` file contains blank configuration guidance only.

### Streamlit Community Cloud — execute only when publication is approved

1. Sign in to https://share.streamlit.io using GitHub and authorise access to the
   repository. Use the free Community Cloud service.
2. Choose **Create app**, select the repository and branch **main**, and set the
   entry-point file to **cloud_app.py** (at the repository root).
3. In **Advanced settings**, select **Python 3.11**, matching the tested 3.11.9
   environment. Leave **Secrets empty**; no Ollama host or API keys are required.
4. Choose an available app subdomain, then **Deploy**. Community Cloud installs
   the root `requirements.txt`; no `packages.txt` or system packages are required.
5. Open the resulting `https://<chosen-name>.streamlit.app` URL in a private browser
   window. Confirm the DEMO banner, synthetic explorer, benchmark cohort selector,
   charts and session-only review form; confirm no research/import/model controls.
   Ensure app sharing permits public viewing, then share the URL with the group.

Official instructions: [deployment and Python settings](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
and [dependency handling](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies).
Cloud Linux startup/build remains to be verified on deployment; current checks run
on Windows/Python 3.11. No repository, remote or deployment was created by this work.

## Evidence and analysis deliverables

The existing Brand Contagion Analysis page now includes **Verified timeline**,
**Synthetic AI case study** and **Strategic implications** tabs. Research panels
hide empty filters, charts and validation matrices when their underlying records
or human labels do not exist. The original synthetic-reference demonstration
remains separate from actual recorded AI predictions.

- `docs/CONTROVERSY_TIMELINE.md` and `demo/research_timeline.json`: 15 dated,
  sourced context entries from 2023 through 16 November 2026. Company statements,
  reported allegations and official inquiries are distinguished; no full articles
  or customer comments are stored or imported into the research database.
- `tests/fixtures/contagion_case_study_24.json`: 24 distinct authored synthetic
  scenarios, with reference labels frozen before inference.
- `demo/case_study_results.json`: actual local Qwen2.5:3b responses, including
  rejected predictions, errors, references, timing and provenance. These are the
  only newly allowlisted raw outputs and contain synthetic material only. Raw
  historical benchmark logs and research data remain ignored.
- `docs/AI_EVALUATION_SUMMARY.md`: existing v1/v2 scores, raw versus accepted
  interpretations, rejection rates, false positives and the new case-study scores.
- `docs/STRATEGIC_IMPLICATIONS.md`: values-based discussion and proposed actions
  through 2030; interpretations and hypotheses are not empirical brand findings.

All evidence and recorded outputs render offline in cloud demo mode without
Ollama, network requests or research SQLite access. Launch locally using the
existing `cloud_app.py` command above. No changes are published automatically.
For a new, explicitly requested synthetic inference run with an already installed
model, use a new filename to preserve the existing run:

```powershell
.venv\Scripts\python scripts/run_case_study.py --output benchmarks/case_study_repeat.json
```

The runner uses an isolated temporary database, never the research database. It
does not change the prompt, download models, or automatically overwrite results.

## Collection workflow

1. Download the CSV template, or upload a CSV/JSON dataset.
2. Review detected mappings, source defaults, numeric date order, and the fixed
   UTC offset for naive dates. Dates with explicit timezone offsets are preferred.
3. Validate all rows, inspect the first ten accepted records and row-level errors,
   then confirm importing valid records. Rejected rows are not stored.
4. For recent news, search GDELT and confirm the displayed snapshot. Importing a
   snapshot does not refetch the API. Repeated records are deduplicated.
5. Filter and export real records in Dataset explorer; review batches in Import history.

The GDELT connector supports a rolling ~90-day window and at most 250 articles
per request. Headlines and metadata are retained, not full article bodies. Use
CSV/JSON for older research evidence. Synthetic records and batches are excluded
from the interface's research dataset and default metrics.

## Guardian historical news

**Disabled pending licence clarification.** `GUARDIAN_ENABLED = False` blocks
preview requests and imports, including programmatic calls and saved previews.
Credentials or a permission-reference string do not enable the connector. Do not
configure placeholder references. The UI explains the permission needed for this
research use. Existing connector behavior is preserved behind the block and tested
only through mocks; no live collection is authorized with a standard developer key.

The following configuration/workflow is retained for a future explicitly approved
release; it does not enable collection in this release.

Set `GUARDIAN_API_KEY` in the environment of the shell launching Streamlit. The
application does not automatically load `.env`. Do not commit or paste the key
into source files, query inputs, screenshots or issue reports.

Set `GUARDIAN_PERMISSION_REFERENCE` to the reference for the applicable research
authorization covering this project's analysis and intended retention. Consult the
[Guardian terms](https://www.theguardian.com/open-platform/terms-and-conditions)
and the terms attached to your key; a developer key alone is not that authorization.
The connector does not implement automatic refresh/deletion. Meet the applicable
retention obligations before using permanent research storage.

Launch the app with the command above and open **Guardian news**. Select a preset
or custom query, inclusive start/end dates (including 2023–2026), result cap and
starting page. Search explicitly, review the snapshot and confirm import. Only
headlines and whitelisted metadata are requested/persisted, with
`content_scope=headline_only` and `collection_method=Guardian API`. Publisher,
byline when available, original publication date, provider article ID, source URL,
retrieval time, search range/page and permission reference remain in `raw_payload`.
An import never makes another API request. Repeated/cross-GDELT URLs deduplicate;
the original canonical record's provenance is preserved rather than overwritten.

Requests are paced at no more than one per second across this running process,
with a local 500-request/day budget and bounded server-error retries. Quota errors
stop collection. The budget resets on restart and cannot account for other tools
or processes using the same key; the provider's quota remains authoritative.
Maximum 1,000 results per preview, 50 per page. Result limits include rejected
articles. For continuation, preserve the page size shown in the preview (choose
the same result cap); a partially consumed page is repeated and overlaps deduplicate.
Failed searches cannot be imported. No real articles are bundled as demo records.

## Tests

For reproducible real-data collection, source access conditions, blank source
templates and the read-only preflight command, see
[the research collection guide](docs/RESEARCH_COLLECTION_GUIDE.md).

```powershell
.venv\Scripts\python -B -m unittest discover -s tests -v
```

## Phase 3: local brand-contagion analysis (backend only)

No new dependencies. `src/analysis/` contains the schema, Ollama transport, engine,
append-only storage, evaluation and package initializer. Existing relevance flags
remain separate from sentiment/spillover predictions. Nothing classifies records
automatically; the Phase 4 dashboard invokes the backend only on explicit confirmation.

For an already-installed Ollama executable and a previously approved/downloaded
local GGUF model, quit any existing Ollama instance and launch it in PowerShell:

```powershell
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_NO_CLOUD = "1"
ollama serve
```

In another shell, `ollama list` shows installed tags. This implementation does not
install Ollama, pull models, call cloud services or silently use rule labels. A
model download requires separate approval. The daemon and host must be trusted;
keep cloud disabled and do not expose the daemon externally. The transport accepts
literal loopback addresses only, bypasses environment proxies, refuses redirects
and checks installed GGUF metadata before transmitting discussion text.

Use the backend explicitly from Python, with actual verified values:

```python
from src.analysis.storage import init_analysis_db, record_permission, append_review, get_history
from src.analysis.engine import classify_record, classify_batch
from src.analysis.evaluation import evaluate_research

init_analysis_db()  # additive tables; existing records are preserved
# record_id, actual_permission_reference, actual_verifier and installed_model_tag
# must refer to your authorized record, documented permission and installed model.
record_permission(record_id, actual_permission_reference, actual_verifier, verified=True)
prediction = classify_record(record_id, installed_model_tag)
# Or: classify_batch(explicit_record_ids, installed_model_tag)
if prediction["status"] == "success":
    append_review(prediction["attempt_id"], human_corrected_labels,
                  reviewer_identifier, human_review_reason)
history = get_history(record_id)
metrics = evaluate_research()
```

The verifier must establish permission for local AI inference, human review and
retention of outputs. A nonempty reference is an audit record of that verification,
not a way to create legal permission. No cloud transfer or model-training rights
are inferred. Real records without a verified grant are blocked before inference;
media and invalid records are excluded. Revoke by appending a permission event via
`record_permission(..., verified=True, revoke=True)`. Regranting requires a new
classification before the record re-enters research summaries. Permission and
input hashes are rechecked before inference and atomically before persistence.

`classification_permissions`, `classification_attempts` and `human_reviews` have
foreign keys and update/delete-blocking triggers. New runs and human corrections
append rows; original source text and original AI output are never overwritten.
Attempts preserve model name/digest, runtime and prompt versions, exact input hash,
timestamp, raw output, accepted labels or failure status. Raw output may contain
source quotations and must receive the same access/retention protections. Revocation
blocks processing and research metrics; legally required erasure/retention scheduling
needs a separate controlled process and is not implemented by this append-only API.

Labels use the requested enums plus `evidence_quotes` (1–5 exact source substrings).
Target `both` means multiple named targets; responsibility `both` means Ray-Ban
and Meta. The default prompt version is `brand-contagion-2.0.0`. Product criticism alone
cannot satisfy explicit spillover: conservative English clause-level evidence checks
require core-brand rejection connected to the controversy. These checks can reject
legitimate paraphrases or non-English expressions; failures remain failed attempts
for review rather than fabricated labels. They do not prove semantic correctness.
Ambiguity/sarcasm should remain `unclear`; implicit spillover is suggestive textual
evidence, not a claim of statistical correlation. Rationale/evidence interpretation
still requires human validation. Very long discussions may exceed the chosen model's
context; select an appropriate model/context and do not interpret failed output.

Confidence is uncalibrated. Confidence below 0.7, unclear targets and explicit,
implicit or unclear spillover set `needs_review`; every explicit finding therefore
requires attention. This is a research-triage flag, not an assertion of accuracy.
Evaluation pairs the latest successful AI run per currently permitted real record
with the latest review of that run. Failed re-runs do not erase prior valid runs;
reviews of an older run are not transferred to a new run. Reported metrics include
per-class and topic precision/recall/F1, accuracy, confusion counts and support, with
explicit-spillover metrics first. Undefined ratios are `None`, not invented zeros.
Model/prompt versions and reviewed/unreviewed counts accompany research evaluation;
do not treat selectively reviewed examples as an unbiased accuracy sample.

Clearly marked invented examples live only in `tests/fixtures/synthetic_contagion.json`.
The deterministic adapter is only in `tests/contagion_support.py`, requires synthetic
records and stores `method=rule_based_test`. Production has no rule fallback.
Research metrics exclude synthetic records and rule-test runs. The complete suite
uses mocked Ollama responses and temporary databases; it measures implementation
correctness, not real-world AI accuracy. No real data have been classified by these tests.

## Phase 4: Brand Contagion Analysis dashboard

Prompt reproducibility: exact v1 and sequential-decision v2 templates are preserved
in `src/analysis/prompts/`. Call `classify_record(...,
prompt_version="brand-contagion-1.0.0")` to select v1 explicitly; each attempt records
the version actually used. JSON/evidence validation and permission safeguards are
unchanged. Prompt v2 separates sentiment/target, responsibility, spillover and purchase
intent, with contrasting examples for negation, sarcasm and mixed views.

`tests/fixtures/contagion_regression_20.json` preserves all 20 Phase 5 examples and
reference labels verbatim. `contagion_heldout_20.json` contains 20 distinct additional
synthetic examples frozen after prompt authoring and before inference, never used
for tuning. Both sets have checked SHA-256 fingerprints. The original v1 regression
summary is retained in `contagion_baseline_v1_summary.json`.

To reproduce the live synthetic-only comparison with an installed local model:

```powershell
.venv\Scripts\python -B scripts/benchmark_contagion.py --output benchmarks/contagion_prompt_v2.json
```

This makes 60 local calls: v2 on regression, then paired v1/v2 held-out calls with
alternating order. It never uses research storage or downloads models. Inputs and
prompts are fingerprinted before inference; a prompt edit during the run aborts it.
Results are checkpointed with raw outputs, model/runtime identity, validation errors,
reference labels and wall time. Raw-label scores and accepted-output scores are kept
separate; rejected predictions are abstentions, not automatically negative labels.
Historical v1 regression timing includes its original machine load/cold-start state,
so paired held-out measurements provide the more controlled comparison. These small,
hand-labelled synthetic sets diagnose errors; they do not establish real-world accuracy.

Launch with `.venv\Scripts\python -m streamlit run app.py` and select **Brand
Contagion Analysis** in the sidebar. No new dependencies or model downloads are
required. The Data Collection Centre remains available.

- **Research** mode selects only real, valid customer discussions with active,
  verified AI permissions. **Check local Ollama** fetches metadata only; select an
  installed model and explicitly confirm one comment or up to 50 approved records.
  Permission and local-model checks still run in the backend for every inference.
- **Customer voice** provides search/label filters, original source links/text,
  escaped quotation highlighting, versioned AI outputs and separate human labels.
- **Human validation** appends complete corrections or confirmations, including
  exact evidence, reviewer identifier and reason; original predictions remain intact.
  History includes previous attempts and reviews. Permission grants are not created
  through this dashboard: verify actual authorization through the backend workflow.
- **Contagion analytics** uses human-reviewed labels only. The rate's numerator
  counts explicit spillover *within* negative privacy-topic discussions; mixed
  sentiment and other topics are outside that denominator. Percentages are hidden
  below 20 denominator records. Sentiment comparison includes only exclusive product
  or core-brand targets, since `both` has no separate per-target sentiment labels.
  Charts use counts and publication years, not population estimates or causal claims.
- Validation's headline metrics require 20 reviewed records and 5 human explicit
  positives. Raw descriptive metrics and confusion counts remain inspectable. These
  thresholds are display safeguards, not statistical guarantees; convenience reviews
  are not a representative evaluation sample.
- **Synthetic demo** loads the existing marked test fixtures without Ollama or
  SQLite writes. Curated reference labels are explicitly *not AI predictions*.
  Demo human corrections are session-only; simulated agreement is not AI accuracy.
  Fixtures have no publication dates or source URLs, so no historical trend is
  invented. Research and demo labels, corrections and metrics remain separate.

No database queries or research labels are cached. Refresh reloads current permission,
prediction and review state; it never triggers inference. Model connection status is
an explicit snapshot and is rechecked by the backend before inference. Streamlit
interaction checks use synthetic records in isolated databases and mocked local models.

Local research mode has no authentication and must remain on localhost. Only the
forced synthetic `cloud_app.py` entry point is prepared for public demonstration.
The explorer loads matching records into memory, making this first version suitable
for research-sized datasets. Reddit ingestion and Strategy Lab are outside this
release. No paid API credentials are required.

### Reviewing the local real-media dataset

Launch the local application on localhost (not `cloud_app.py`):

```powershell
$env:RAYBAN_APP_MODE = "local"
.venv\Scripts\python -m streamlit run app.py --server.address 127.0.0.1
```

Open **Brand Contagion Analysis > Real Media Evidence**. The article queue uses
`data/research_news_2023_2026/human_review_template.csv`; keep its source IDs,
fingerprints and proposal snapshots unchanged. The private dataset must already
exist locally; it is not included in a public checkout.

1. Enter your reviewer name or agreed team identifier. Select an article and open
   its original source. Compare the date, publisher, headline, proposed labels,
   evidence and flags with the source context. No source content is fetched automatically.
2. Explicitly choose **Confirm proposed labels**, **Correct classifications**,
   **Mark uncertain**, or **Exclude from analysis**. Correct individual fields as
   needed and record supporting evidence and a short justification, including any
   access limitations. Use uncertainty rather than guessing when verification is blocked.
3. Check the source-evidence attestation and select **Save media review**. The
   application appends an event with an automatic UTC timestamp to the existing
   `media_review_events.csv`. Refresh never approves a record. Uncheck the
   pending-only filter to inspect history or append a later correction.
4. Use **Export completed media reviews (CSV)** for the latest resolved decision
   per article, including exclusions. Pending and uncertain cases are omitted;
   spreadsheet formula-like cells are escaped only in the download.

Reviewed coverage includes confirm/correct/exclude decisions. Uncertain decisions
remain pending and flagged. **Disagreements** counts latest label corrections
against proposals plus exclusions; it does not measure agreement between reviewers.
Reviewed findings use only current confirmed/corrected labels, separately from
provisional counts. An explicit wider-brand reference can be positive or stylistic:
it is not evidence of brand damage. An allegation or inquiry is not proven liability.

The append-only ledger preserves earlier decisions and original classifications.
An OS file lock protects concurrent saves on one filesystem; stale saves are
rejected. This is a local, unauthenticated team workflow, not a tamper-proof or
multi-host review service. Protect the ignored data directory and keep backups;
reviewer identity and actual source checks remain the team's responsibility.
Demo/cloud mode cannot save or export named reviews. Preparation-time summary
CSV/JSON files are snapshots; the dashboard recomputes current findings from the
ledger and the completed-review download reflects current decisions.
