# AI evaluation summary - synthetic demonstrations only

This report uses existing recorded benchmark files and the new actual local 24-case run. No performance number is inferred from fixture labels alone. No real customer records were classified.

## Existing v1 versus v2 benchmark

Source: `demo/benchmark_summary.json`, copied from the existing `benchmarks/contagion_prompt_v2_summary.json`. The regression v1 baseline predates the paired comparison. Each cohort has 20 authored synthetic examples.

| Cohort / prompt | Sentiment | Target | Responsibility | Spillover (4-way) | Purchase intent | Topic exact set | Explicit P / R / F1 | Accepted | Rejected | Mean seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| regression_v1 | 90.0% | 45.0% | 15.0% | 60.0% | 95.0% | 15.0% | 36.4% / 100.0% / 53.3% | 9/20 | 11/20 (55.0%) | 15.22 |
| regression:brand-contagion-2.0.0 | 85.0% | 80.0% | 85.0% | 80.0% | 100.0% | 20.0% | 80.0% / 100.0% / 88.9% | 17/20 | 3/20 (15.0%) | 19.07 |
| heldout:brand-contagion-1.0.0 | 75.0% | 45.0% | 15.0% | 45.0% | 75.0% | 35.0% | 44.4% / 80.0% / 57.1% | 11/20 | 9/20 (45.0%) | 14.13 |
| heldout:brand-contagion-2.0.0 | 75.0% | 80.0% | 85.0% | 95.0% | 90.0% | 30.0% | 83.3% / 100.0% / 90.9% | 16/20 | 4/20 (20.0%) | 16.58 |

All table label scores use raw evaluable outputs, including predictions later rejected by application safeguards. Accepted counts are operational acceptance, not correctness. False positives and false negatives below are explicit spillover versus all other spillover labels.

### False-positive examples and safeguard limits

**regression_v1:** raw FP=7, raw FN=0. False-positive cases: product_only, meta_only, sarcasm, rayban_blame, product_purchase_rejection, meta_blame_brand_defence, product_sarcasm.

Synthetic example: Ray-Ban Meta glasses have a terrible recording light. I returned these smart glasses.
Reference spillover: `none`; raw model prediction: `explicit`.

**regression:brand-contagion-2.0.0:** raw FP=1, raw FN=0. False-positive cases: rayban_blame.

Synthetic example: Ray-Ban is responsible for putting cameras in the smart glasses. The recording feature is unsafe.
Reference spillover: `none`; raw model prediction: `explicit`.

**heldout:brand-contagion-1.0.0:** raw FP=5, raw FN=1. False-positive cases: held_negated_rayban_blame, held_rayban_only_blame, held_shared_product_accountability, held_unspecified_sarcasm, held_core_purchase_despite_distrust.

Synthetic example: Only Meta is responsible for gathering voice data; Ray-Ban is not at fault.
Reference spillover: `none`; raw model prediction: `explicit`.

**heldout:brand-contagion-2.0.0:** raw FP=1, raw FN=0. False-positive cases: held_shared_product_accountability.

Synthetic example: I hold Meta and Ray-Ban equally responsible for the glasses camera secretly recording people.
Reference spillover: `none`; raw model prediction: `explicit`.

Rejections also remove some reference-positive predictions: the stored v2 held-out summary lists two reference-explicit cases among four rejected outputs. Rejected records must remain abstentions, not be silently relabelled negative.

## New 24-case illustrative study

References were authored and fingerprinted before inference. These cases were not used to change the prompt, and are distinct from both earlier 20-case sets. They are an illustrative study, not a newly independent population benchmark.

Model: `qwen2.5:3b`; model digest `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`; Ollama `0.40.16`; prompt `brand-contagion-2.0.0`.
Recorded UTC: 2026-11-16T16:12:26.966949+00:00. Fixture SHA-256: `1c4f63531da055f189a604ceee361e49275728479dee3f5f662e8dd0a316f2b7`. Prompt SHA-256: `bc3d69e588928e0c580c00d8099beb02c58a61c12735d160d811225f00f1c5b3`.

| Field | Raw accuracy | Accepted-subset accuracy |
| --- | --- | --- |
| sentiment | 91.7% | 90.9% |
| target | 54.2% | 59.1% |
| responsibility | 75.0% | 77.3% |
| spillover | 91.7% | 95.5% |
| purchase_intent | 95.8% | 100.0% |

Topic exact-set match (raw): 16.7%.
Attempts: 24; label-evaluable: 24; accepted: 22; rejected: 2 (8.3%). Mean wall time: 14.09s; median: 12.23s per comment. Timing includes per-record model inspection; the first call may include cold-start costs.

| Explicit spillover | TP | FP | FN | TN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Raw evaluable (24) | 5 | 1 | 0 | 18 | 83.3% | 100.0% | 90.9% |
| Accepted subset (22) | 5 | 0 | 0 | 17 | 100.0% | 100.0% | 100.0% |

The accepted-subset values are conditional on non-rejection and do not describe all attempted inputs or real-world performance.

### Observed case errors - preserved, not repaired

- `case24_sarcasm_unspecified`: rejected. Explicit spillover requires quoted core-brand distrust linked to the controversy; otherwise use unclear/implicit.
- `case24_neutral_question`: rejected. Evidence quotations must be exact nonempty substrings of the original text.

- `case24_meta_data`: the accepted output labels Meta-only criticism as **implicit** spillover and invents a rationale about wider Ray-Ban distrust. The quoted text does not support that extension. Schema acceptance does not establish semantic validity.
- Six responsibility errors assign Meta where the reference is unclear. Brand mentions or controversy context are not explicit attribution.
- Target accuracy remains weak: product/core-brand/both distinctions are often confused. Two mixed examples are labelled negative. Topic exact-set agreement is low.
- `case24_sarcasm_unspecified`: raw explicit-spillover false positive; safeguards reject unsupported brand rejection. No raw explicit false negatives occurred in this 24-case run.
- `case24_neutral_question`: the model shortens an evidence quotation; exact-substring validation rejects it even though its spillover label matches the reference.

## Audit: accepted predictions and positive-case coverage

All 104 saved raw JSON responses were reparsed, rather than trusting cached parsed responses or summary scores. They represent 64 distinct authored texts: 20 regression, 20 held-out and 24 case-study scenarios. Paired v1/v2 predictions are repeated measurements of the same texts, not additional independent examples. All 104 contain evaluable category labels. Label accuracies, topic exact-set match, binary confusion counts, timing, false-positive/negative identifiers and acceptance counts were checked against saved artifacts. No new inference was run.

| Cohort | Accepted / attempted | Reference-explicit cases retained | Accepted explicit P / R / F1 | Accepted true positives / all reference-explicit cases |
| --- | --- | --- | --- | --- |
| regression_v1 | 9/20 | 0/4 | undefined / undefined / undefined | 0/4 |
| regression:brand-contagion-2.0.0 | 17/20 | 2/4 | 100.0% / 100.0% / 100.0% | 2/4 |
| heldout:brand-contagion-1.0.0 | 11/20 | 1/5 | undefined / 0.0% / 0.0% | 0/5 |
| heldout:brand-contagion-2.0.0 | 16/20 | 3/5 | 100.0% / 100.0% / 100.0% | 3/5 |
| case_study_24 | 22/24 | 5/5 | 100.0% / 100.0% / 100.0% | 5/5 |

Accepted-subset recall conditions on the retained reference-positive cases. For example, v2 held-out accepted recall is 100% on **three retained positives**, while only **3/5** originally positive inputs yield an accepted correct explicit label. That 3/5 is an end-to-end positive yield with abstentions; it is not a replacement for the raw-label recall or a reclassification of abstentions as negatives. Undefined ratios remain undefined. No accepted explicit-positive validation was available in the v1 regression subset.

The historical comparison table above scores all 20 evaluable outputs in each cohort, including rejected outputs. Its four-way spillover accuracy differs from binary explicit-versus-other accuracy. Confidence scores and rationales are not accuracy measures.

## Methodological limitations

Synthetic English examples are small, purposive and hand-labelled by one author; there is no independent inter-rater validation. Matching the author reference is not ground truth about real customers. Original regression v1 timing is not directly controlled against later v2 runs; alternating held-out order is more comparable but still hardware-specific. Prompts and reference sets can be familiar to the author, and subject-matter coverage is narrow. Confidence is uncalibrated. JSON validation and evidence matching cannot validate every rationale or implicit-spillover inference. No prompt, safeguard or reference-label changes were made to improve these results.

Actual raw strings, parsed responses, reference labels, errors, acceptance flags and model/prompt provenance are preserved in `demo/case_study_results.json`. The synthetic fixture is `tests/fixtures/contagion_case_study_24.json`. Re-run explicitly with a new output path using `python scripts/run_case_study.py --output benchmarks/case_study_repeat.json`; an existing output is never overwritten. No classification runs on dashboard refresh.
