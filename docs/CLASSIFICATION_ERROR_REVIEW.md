# Final classification review — 20 November 2026

This is an **AI-assisted editorial proposal review, not independent human validation**.
No new customer comments, model downloads or inference calls were made. Original
scenario CSV/JSON, all 260 model responses, the verified timeline, 32-source manifest
and historical benchmark files retain their original byte hashes.

## Why explicit spillover is missed

The saved run remains 260 attempts, 220 accepted, 40 rejected, with 52.3% raw
spillover agreement against unvalidated design intentions. Of 28 raw explicit
predictions, 26 disagree with design labels and two agree. All 28 failed the
historical safeguards. Thus zero accepted explicit predictions is not evidence
that wider-brand contagion is absent.

There are three distinct problems:

1. **Design labels sometimes contradict the wording.** SIM-0064 switches away
   from smart glasses toward regular frames; SIM-0066 prefers traditional Ray-Ban;
   SIM-0073 expressly trusts the traditional brand. Calling these explicit negative
   wider-brand spillover would be misleading. Trust and wearing preference also
   do not automatically establish purchase intention or company-specific blame.
2. **The model frequently chooses implicit or none instead of explicit.**
   SIM-0068 directly states that privacy concerns prevent wanting to wear regular
   frames. SIM-0080 explicitly says privacy issues spill over into not wanting
   regular eyewear. Both raw predictions were implicit: a validator change alone
   cannot recover labels the model never emitted.
3. **Exact quotations and conservative lexical rules matter.** Fourteen of the
   40 failures have inexact evidence quotations; 19 assert explicit spillover with
   a product/Meta-only target; seven lack the required quoted causal core-brand
   distrust. SIM-0078 appends a full stop to a substring that originally continues
   with a comma: the quote rejection is justified. SIM-0070 retains core trust and
   uses ambiguous “their glasses”; SIM-0071's quoted passage lacks a decisive causal
   core-brand rejection. These are not reasons to auto-accept historical outputs.

## Stratified proposal sample

The reproducible sample contains all 30 designed-explicit cases (SIM-0061–0090),
10 product/Meta criticism cases (SIM-0001, 0007, 0013, 0019, 0025, 0031, 0037,
0043, 0049, 0055), and ten implicit/protection cases (SIM-0091, 0097, 0103, 0109,
0115, 0121, 0133, 0145, 0157, 0169). Selection does not depend on acceptance or
classification correctness and covers simulated years 2023–2026.

Among the 30 designed-explicit cases, the review proposes **12 explicit, 10 implicit,
6 none and 2 unclear**. Across all 50, the proposals contain 12 explicit, 12 implicit,
22 none and four unclear. These counts are proposals on a deliberately stratified
sample, not estimates for all 260 scenarios and not a revised accuracy benchmark.

Qualified distrust can be explicit when the text directly states the transfer to
ordinary eyewear. Future possibilities, unresolved questions and traditional-brand
defence remain distinct. Each proposal includes the original text, exact evidence,
all proposed labels, a justification, uncertainty flag, original design labels,
historical model labels/status and separate evidence-rule replay. All await human
review. There is no human reviewer identity or approval fabricated in the dataset.

## Versioned correction without rewriting history

`validate_labels` retains `legacy-1.0` as its default. The existing inference engine
and historical replay continue using that rule, preserving the 220/40 split and
all previous prompt/benchmark versions. An **opt-in** `context-evidence-2.0` rule
recognises direct, text-supported forms such as qualified distrust after privacy
concerns and privacy-linked avoidance of regular eyewear (SIM-0068 and SIM-0080).
It still requires exact quotations, core scope, an adverse predicate and a causal
controversy link. Product-only criticism, core-brand praise, negated distrust and
mere adjacency do not qualify. This is an evidence-rule correction, not a new
model run or retroactive approval of rejected predictions.

The 50-case sidecar is `demo/classification_review_proposals.json` / `.csv`.
Rebuild it with `python scripts/prepare_classification_review.py`. Its source hashes
bind it to unchanged historical artefacts. The public Model evaluation tab exposes
it separately; proposals never replace predictions or feed research metrics.

Independent human coding would be needed before calling these corrections gold
labels or interpreting agreement as validated model accuracy. No claim of empirical
customer sentiment, historical sentiment trends or causal brand damage is supported.
