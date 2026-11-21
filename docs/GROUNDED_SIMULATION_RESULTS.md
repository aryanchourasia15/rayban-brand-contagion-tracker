# Grounded synthetic demonstration: recorded results

**AI-generated customer scenarios — illustrative, not empirical customer sentiment.**

Final scenarios: 260. Recorded classifications: 260; accepted 220; rejected 40; categorical-evaluable raw 260.

Generation audit: 354 complete comment objects across 354 recorded attempts; 47 drafts selected for pre-classification wording replacement. Development pilots are retained separately and are not part of the final dataset.

References are scenario-design intentions, not independently validated ground truth. Generation and classification use the same local model. Agreement cannot estimate real-world accuracy, customer sentiment, historical trends or actual brand damage.

## Designed corpus, not model findings

| Scenario category | Count |
| --- | ---: |
| privacy_product_criticism | 60 |
| wider_brand_distrust | 60 |
| meta_responsibility_brand_protected | 60 |
| positive_experience | 40 |
| neutral_or_mixed | 40 |

| Design field | Label | Count / total scenarios |
| --- | --- | ---: |
| sentiment | negative | 120/260 |
| sentiment | mixed | 80/260 |
| sentiment | positive | 40/260 |
| sentiment | neutral | 20/260 |
| target | Ray-Ban Meta | 100/260 |
| target | both | 30/260 |
| target | core Ray-Ban | 50/260 |
| target | Meta | 60/260 |
| target | unclear | 20/260 |
| responsibility | Meta | 90/260 |
| responsibility | Ray-Ban | 30/260 |
| responsibility | both | 30/260 |
| responsibility | unclear | 110/260 |
| spillover | none | 180/260 |
| spillover | explicit | 30/260 |
| spillover | implicit | 30/260 |
| spillover | unclear | 20/260 |
| purchase_intent | negative | 90/260 |
| purchase_intent | unclear | 110/260 |
| purchase_intent | positive | 60/260 |

## Model agreement, separate from scenario distributions

| Field | Raw evaluable accuracy | Accepted-only accuracy |
| --- | ---: | ---: |
| sentiment | 66.9% (n=260) | 63.2% (n=220) |
| target | 34.6% (n=260) | 30.9% (n=220) |
| responsibility | 61.2% (n=260) | 65.0% (n=220) |
| spillover | 52.3% (n=260) | 56.8% (n=220) |
| purchase_intent | 66.9% (n=260) | 64.1% (n=220) |

| Explicit-spillover basis | TP | FP | FN | TN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| raw_metrics | 2 | 26 | 28 | 204 | 7.1% | 6.7% | 6.9% |
| accepted_metrics | 0 | 0 | 27 | 193 | undefined | 0.0% | 0.0% |

Raw metrics include rejected outputs only when their categorical fields are evaluable. Accepted-only results are selected by safeguards. Rejections are abstentions, not `none`. Unparseable outputs are absent from raw confusion matrices and remain in the rejection count.

Mean recorded inference time: 16.74 seconds/comment (local machine, not a portable speed claim).

Raw evaluable explicit false positives: SIM-0001, SIM-0002, SIM-0007, SIM-0021, SIM-0023, SIM-0029, SIM-0031, SIM-0032, SIM-0033, SIM-0036, SIM-0037, SIM-0038, SIM-0039, SIM-0042, SIM-0044, SIM-0049, SIM-0050, SIM-0051, SIM-0054, SIM-0055, SIM-0056, SIM-0059, SIM-0060, SIM-0163, SIM-0175, SIM-0192.

Raw evaluable explicit false negatives: SIM-0061, SIM-0062, SIM-0063, SIM-0064, SIM-0065, SIM-0066, SIM-0067, SIM-0068, SIM-0069, SIM-0072, SIM-0073, SIM-0074, SIM-0075, SIM-0076, SIM-0077, SIM-0078, SIM-0079, SIM-0080, SIM-0081, SIM-0082, SIM-0083, SIM-0084, SIM-0085, SIM-0086, SIM-0087, SIM-0088, SIM-0089, SIM-0090.

Rejected design-reference explicit positives: SIM-0070, SIM-0071, SIM-0078.

## Actual accepted-model label counts

| Field | Label | Count / accepted |
| --- | --- | ---: |
| sentiment | negative | 142/220 |
| sentiment | neutral | 20/220 |
| sentiment | mixed | 19/220 |
| sentiment | positive | 39/220 |
| target | Ray-Ban Meta | 67/220 |
| target | unclear | 32/220 |
| target | core Ray-Ban | 72/220 |
| target | both | 38/220 |
| target | Meta | 11/220 |
| responsibility | unclear | 161/220 |
| responsibility | both | 1/220 |
| responsibility | Ray-Ban | 5/220 |
| responsibility | Meta | 53/220 |
| spillover | none | 111/220 |
| spillover | unclear | 33/220 |
| spillover | implicit | 76/220 |
| purchase_intent | unclear | 170/220 |
| purchase_intent | negative | 21/220 |
| purchase_intent | positive | 29/220 |

## Observed limitations of this recorded run

Accepted explicit-spillover predictions: 0. Zero accepted explicit outputs is not evidence of zero real spillover, nor does it rule out Reaction B. Intended scenario labels and accepted model labels remain separate.

Safeguard rejection reasons:

- 19: Product-only/Meta-only criticism cannot establish explicit brand spillover.
- 14: Evidence quotations must be exact nonempty substrings of the original text.
- 7: Explicit spillover requires quoted core-brand distrust linked to the controversy; otherwise use unclear/implicit.

Generation references can disagree with the actual wording, especially target scope, responsibility and explicit versus implicit distrust. Guard acceptance also depends on exact quotations and conservative wording checks. Independent human coding is needed to disentangle reference problems, model errors and safeguard abstentions. This is a different corpus from the fixed v1/v2 benchmarks; their scores are not a paired measure of improvement or decline on these scenarios.


## Raw evaluable confusion matrices

Rows are design references; columns are raw model predictions.

### sentiment

| Reference / predicted | positive | negative | neutral | mixed |
| --- | ---: | ---: | ---: | ---: |
| positive | 34 | 3 | 0 | 3 |
| negative | 0 | 117 | 1 | 2 |
| neutral | 0 | 10 | 9 | 1 |
| mixed | 8 | 48 | 10 | 14 |

### target

| Reference / predicted | Ray-Ban Meta | core Ray-Ban | Meta | both | unclear |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ray-Ban Meta | 55 | 13 | 7 | 9 | 16 |
| core Ray-Ban | 17 | 15 | 2 | 11 | 5 |
| Meta | 7 | 32 | 1 | 20 | 0 |
| both | 8 | 14 | 0 | 8 | 0 |
| unclear | 1 | 0 | 3 | 5 | 11 |

### responsibility

| Reference / predicted | Ray-Ban | Meta | both | unclear |
| --- | ---: | ---: | ---: | ---: |
| Ray-Ban | 5 | 3 | 0 | 22 |
| Meta | 2 | 55 | 0 | 33 |
| both | 3 | 6 | 1 | 20 |
| unclear | 4 | 7 | 1 | 98 |

### spillover

| Reference / predicted | explicit | implicit | none | unclear |
| --- | ---: | ---: | ---: | ---: |
| explicit | 2 | 22 | 6 | 0 |
| implicit | 0 | 20 | 9 | 1 |
| none | 26 | 40 | 98 | 16 |
| unclear | 0 | 0 | 4 | 16 |

### purchase_intent

| Reference / predicted | positive | negative | unclear |
| --- | ---: | ---: | ---: |
| positive | 32 | 3 | 25 |
| negative | 0 | 37 | 53 |
| unclear | 0 | 5 | 105 |

## Reactions A, B and C: illustrative cases, not empirical tests

**Reaction A, SIM-0001 — simulated:** These camera and AI features make these Ray-Ban Meta glasses too invasive. I won't be buying them for privacy reasons.

Design spillover: none; actual raw model spillover: explicit; safeguard status: failed.

**Reaction B, SIM-0061 — simulated:** I'm glad they're considering privacy, but I still can't shake the doubt that Ray-Ban Meta is gathering too much data. It's not just the glasses, it's the whole brand now.

Design spillover: explicit; actual raw model spillover: implicit; safeguard status: success.

**Reaction C, SIM-0121 — simulated:** I get it's innovative, but the privacy concerns still worry me. I trust traditional Ray-Ban, but Meta needs to step up on data security.

Design spillover: none; actual raw model spillover: implicit; safeguard status: success.

## Provenance, diversity and limitations

Source coverage: 32/32 existing references. Simulated year counts: {'2023': 52, '2024': 44, '2025': 92, '2026': 72}.

All public IDs/URLs/dates match the existing bibliographic manifest; no fresh website-availability claim is made. Original articles and human-review events remain separate and unchanged. Only metadata topics and independently written event briefs were sent to local generation, never restricted publisher text.

Lexical checks (not semantic or human validation):

```json
{
  "min_words": 9,
  "max_words": 68,
  "mean_words": 29.49230769230769,
  "unique_four_word_openings": 139,
  "repeated_openings": {
    "the camera and ai": 25,
    "i m hesitant about": 2,
    "camera and ai in": 2,
    "if they re not": 2,
    "the camera in these": 6,
    "if ray ban meta": 8,
    "i m not sure": 2,
    "i don t trust": 4,
    "if they re secretly": 2,
    "i guess i m": 2,
    "i used to love": 11,
    "i still trust traditional": 2,
    "i trust traditional ray": 2,
    "i still appreciate traditional": 3,
    "the smart glasses ai": 8,
    "the partnership sounds promising": 3,
    "while the smart glasses": 2,
    "the smart glasses are": 3,
    "i appreciate the smart": 2,
    "meta holds the responsibility": 4,
    "i see the potential": 3,
    "meta gets the blame": 20,
    "i hear meta gets": 5,
    "while i understand the": 2,
    "can t wait to": 4,
    "these meta smart glasses": 3,
    "i understand the privacy": 9,
    "i see the privacy": 4,
    "i can appreciate the": 2,
    "i get the privacy": 3,
    "i can see the": 2
  },
  "high_similarity_pairs": [
    {
      "left": "SIM-0123",
      "right": "SIM-0125",
      "trigram_jaccard": 0.7222222222222222
    },
    {
      "left": "SIM-0125",
      "right": "SIM-0128",
      "trigram_jaccard": 0.7058823529411765
    },
    {
      "left": "SIM-0125",
      "right": "SIM-0133",
      "trigram_jaccard": 0.6666666666666666
    },
    {
      "left": "SIM-0128",
      "right": "SIM-0133",
      "trigram_jaccard": 0.7222222222222222
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0137",
      "trigram_jaccard": 0.7222222222222222
    },
    {
      "left": "SIM-0137",
      "right": "SIM-0138",
      "trigram_jaccard": 0.6666666666666666
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0140",
      "trigram_jaccard": 0.65
    },
    {
      "left": "SIM-0137",
      "right": "SIM-0140",
      "trigram_jaccard": 0.6363636363636364
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0141",
      "trigram_jaccard": 0.7222222222222222
    },
    {
      "left": "SIM-0137",
      "right": "SIM-0141",
      "trigram_jaccard": 0.7
    },
    {
      "left": "SIM-0140",
      "right": "SIM-0141",
      "trigram_jaccard": 0.8
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0142",
      "trigram_jaccard": 0.6842105263157895
    },
    {
      "left": "SIM-0137",
      "right": "SIM-0142",
      "trigram_jaccard": 0.75
    },
    {
      "left": "SIM-0140",
      "right": "SIM-0142",
      "trigram_jaccard": 0.6086956521739131
    },
    {
      "left": "SIM-0141",
      "right": "SIM-0142",
      "trigram_jaccard": 0.6666666666666666
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0145",
      "trigram_jaccard": 0.9285714285714286
    },
    {
      "left": "SIM-0137",
      "right": "SIM-0145",
      "trigram_jaccard": 0.7647058823529411
    },
    {
      "left": "SIM-0140",
      "right": "SIM-0145",
      "trigram_jaccard": 0.6842105263157895
    },
    {
      "left": "SIM-0141",
      "right": "SIM-0145",
      "trigram_jaccard": 0.7647058823529411
    },
    {
      "left": "SIM-0142",
      "right": "SIM-0145",
      "trigram_jaccard": 0.7222222222222222
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0147",
      "trigram_jaccard": 0.7222222222222222
    },
    {
      "left": "SIM-0137",
      "right": "SIM-0147",
      "trigram_jaccard": 0.8888888888888888
    },
    {
      "left": "SIM-0138",
      "right": "SIM-0147",
      "trigram_jaccard": 0.75
    },
    {
      "left": "SIM-0140",
      "right": "SIM-0147",
      "trigram_jaccard": 0.6363636363636364
    },
    {
      "left": "SIM-0141",
      "right": "SIM-0147",
      "trigram_jaccard": 0.7
    },
    {
      "left": "SIM-0142",
      "right": "SIM-0147",
      "trigram_jaccard": 0.75
    },
    {
      "left": "SIM-0145",
      "right": "SIM-0147",
      "trigram_jaccard": 0.7647058823529411
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0149",
      "trigram_jaccard": 0.7222222222222222
    },
    {
      "left": "SIM-0137",
      "right": "SIM-0149",
      "trigram_jaccard": 0.7
    },
    {
      "left": "SIM-0140",
      "right": "SIM-0149",
      "trigram_jaccard": 0.6363636363636364
    },
    {
      "left": "SIM-0141",
      "right": "SIM-0149",
      "trigram_jaccard": 0.7
    },
    {
      "left": "SIM-0142",
      "right": "SIM-0149",
      "trigram_jaccard": 0.6666666666666666
    },
    {
      "left": "SIM-0145",
      "right": "SIM-0149",
      "trigram_jaccard": 0.7647058823529411
    },
    {
      "left": "SIM-0147",
      "right": "SIM-0149",
      "trigram_jaccard": 0.7
    },
    {
      "left": "SIM-0147",
      "right": "SIM-0150",
      "trigram_jaccard": 0.625
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0153",
      "trigram_jaccard": 0.6086956521739131
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0165",
      "trigram_jaccard": 0.6363636363636364
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0169",
      "trigram_jaccard": 0.6363636363636364
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0170",
      "trigram_jaccard": 0.7777777777777778
    },
    {
      "left": "SIM-0145",
      "right": "SIM-0170",
      "trigram_jaccard": 0.7222222222222222
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0173",
      "trigram_jaccard": 0.7
    },
    {
      "left": "SIM-0137",
      "right": "SIM-0173",
      "trigram_jaccard": 0.6086956521739131
    },
    {
      "left": "SIM-0145",
      "right": "SIM-0173",
      "trigram_jaccard": 0.65
    },
    {
      "left": "SIM-0147",
      "right": "SIM-0173",
      "trigram_jaccard": 0.6086956521739131
    },
    {
      "left": "SIM-0136",
      "right": "SIM-0177",
      "trigram_jaccard": 0.7058823529411765
    },
    {
      "left": "SIM-0145",
      "right": "SIM-0177",
      "trigram_jaccard": 0.6470588235294118
    }
  ],
  "limitation": "Heuristic lexical checks do not establish naturalness, representativeness or semantic reference-label validity."
}
```

Structural generation rejections and pilot selection precede classifier evaluation. They improve presentation quality without establishing reference-label validity. Some wording may depart from its planned label; responsibility/target ambiguity and safeguards can therefore reduce agreement. No references were changed after observing classifier outputs.

Model: qwen2.5:3b; digest: `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`; classification prompt: `brand-contagion-2.0.0`; dataset fingerprint: `31f1d3fa56f5714fab7972ac05d7da8d17e40160ee57006f7cb5a9643d88d8bb`.

See SYNTHETIC_DEMONSTRATION.md for the full methodology and STRATEGIC_IMPLICATIONS.md for conditional recommendations.
