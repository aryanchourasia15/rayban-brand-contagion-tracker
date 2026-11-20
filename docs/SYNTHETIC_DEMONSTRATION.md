# Grounded synthetic customer demonstration

**AI-generated customer scenarios — illustrative, not empirical customer sentiment.**

The professor-approved demonstration illustrates H1/H2/H3 mechanisms without real
customer collection. The original 32 media records and review ledger stay separate.

## Design and artefacts

The planned 260 scenarios comprise 60 privacy/product criticisms, 60 wider-brand
distrust reactions (30 explicit and 30 implicit design labels), 60 Meta-responsibility
reactions protecting traditional Ray-Ban, 40 positive and 40 neutral/mixed reactions.
These quotas are deliberate, not estimates of customer attitudes. Reference labels
are intentions supplied to the generator, not independent annotations of its text;
generated wording can depart from them. The same Qwen2.5:3b model subsequently
classifies the comments without seeing those labels. Agreement is circular,
in-sample diagnostic consistency, not independently validated or held-out accuracy.

| Public artefact | Contents |
| --- | --- |
| `demo/media_sources.json` | Allowlisted IDs, original URLs, dates, publishers, titles, topics, evidence types and timeline links for 32 genuine sources. |
| `demo/grounded_scenarios.json` and `.csv` | Marked simulations, `SIM-` IDs, simulated dates, source/event links, provisional design labels and model/prompt provenance. |
| `demo/simulation_generation.json` | Frozen plan, actual local outputs, input payloads, seeds, timings and structural rejections. Development pilots remain under ignored `benchmarks/`. |
| `demo/simulation_classifications.json` | Actual unchanged-engine outputs, raw JSON, errors, safeguard decisions, timing and recomputable evaluation tables. |

## Context and safety

Only bibliographic topics and independently written sourced timeline briefs go to
generation. No article bodies, restricted passages, private media-coding evidence,
reviewer names or real customer comments are processed. Original source-text
permission flags are not overridden. Allegations and inquiries are not proven
liability. The source manifest retains the collection's verification status;
matching all 32 IDs, URLs and dates is a provenance audit, not fresh web verification.
During this run, 32 header-only availability checks failed with connection errors
in the execution environment. No restrictions were bypassed and no article bodies
were retrieved. Current link availability therefore remains unverified; the
existing collection's dated source checks are retained.

Simulated dates are on/after linked articles and events, through the frozen
19 November 2026 cutoff. Year filters provide narrative context, not historical
customer trends. There are no authentic customer URLs, usernames or engagement
counts. Normalized duplicates and fabricated URLs/handles are rejected. Requested
styles, lengths and perspectives vary; lexical checks report repeated openings
and similar trigrams. These checks do not establish naturalness, factual accuracy,
representativeness or semantic validity of the generation references.

CSV exports carry explicit synthetic markers; the importer rejects marked rows in
real-data mode and requires explicit synthetic ingestion. Public Streamlit reads
only curated `demo/` artefacts, without Ollama, credentials, private files, research
databases or persistent writable storage. Classification uses a temporary,
synthetic-only SQLite database with unchanged evidence safeguards.

## Reproduce locally

With Qwen2.5:3b already installed and Ollama listening on loopback:

```powershell
.venv\Scripts\python scripts/build_grounded_demo.py --stage generate
.venv\Scripts\python scripts/build_grounded_demo.py --stage repair
.venv\Scripts\python scripts/build_grounded_demo.py --stage classify
```

Both stages checkpoint and resume without silently regenerating completed outputs.
Frozen-input, prompt and model/runtime mismatches stop a mixed-provenance run.
Preserve artefacts separately before intentionally starting a new run. Actual
seeds/outputs are recorded; identical output across hardware/runtime versions is
not guaranteed. Generation can use the public source manifest if private media
files are absent. No models are downloaded and no cloud inference is available.
The repair stage is a pre-classification wording screen for missing Meta/core-brand
distinctions, not an evaluation-based selection. It archives the initial corpus,
preserves all original raw outputs and records replacement reasons without changing
design labels. It is blocked after inference starts. If interrupted, resume with
`--stage generate`; the saved content-check policy remains active. Lexical inclusion
still does not establish semantic label correctness or independent validation.

## Interpretation

Main charts explicitly select **design references** or **accepted local AI
predictions**. The latter omits rejections/unattempted cases rather than filling
gaps with references; its denominator is displayed. Category comparisons still
refer to assigned scenario categories. The inspector shows actual model outputs
separately, including failures in reference-view mode. Evaluation uses the full recorded
run, unaffected by display filters. Raw metrics include categorical-evaluable
rejected outputs; accepted-only metrics have a selected denominator. Rejections
are abstentions, not automatically `none`. Confusion matrices use reference rows
and prediction columns. Undefined metrics are null, not invented zeros/perfection.

H1 illustrates product-specific concern; H2 a possible transfer through perceived
endorsement and conflicting brand values; H3 preserved trust in ordinary eyewear
alongside Meta-focused blame. Genuine media provides context. Neither simulations
nor model agreement establishes real reputational damage or tests these hypotheses
empirically. See `STRATEGIC_IMPLICATIONS.md` for conditional recommendations to 2030.

Recorded agreement metrics and examples are in
[GROUNDED_SIMULATION_RESULTS.md](GROUNDED_SIMULATION_RESULTS.md), generated from
saved inference outputs only after the full local run completes.
