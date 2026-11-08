# EchoMind research progress — v0.3 and v0.4

**Status as of 2026-11-08:** Exploratory local pilots completed; independent human-behavioral fidelity validation is **not** complete.

> **Provenance:** This document summarizes local AGY/Work execution reports and the researcher's review. Counts and observations below are reported results from isolated local runs; the v0.4 SQLite database, raw model traces, and the exact local v0.3/v0.4 source snapshots have **not** been committed to this repository or independently re-run from this GitHub revision. Do not treat this branch as a runnable reproduction of v0.4.

## Research question

Can controlled memory/context injection change an LLM agent's interpretation of ambiguous situations in a psychologically meaningful and transferable way, and eventually reproduce **empirically measured human response patterns**?

The existing agent produces three fields: `interpretation`, `speech`, and `action`. Experimental memory conditions are: no-context baseline plus neutral/negative events delivered as `direct`, `transcript`, or `interactive` context. Evaluation uses three ambiguous social situations (S1–S3) and one nonsocial printer control (S4). These are *researcher-authored* scenarios, not a human-validated scale.

**Optimization criterion:** closer agreement with a suitable human response distribution, not simply more negative, less negative, or more fluent text. At present, the human reference needed for a quantitative fidelity score is missing.

## v0.3 — Prompt-framing ablation

- **Variable:** P0 = original response instruction; P1 = identical instruction with one appended sentence asking for a natural everyday response.
- **Controls:** same seven context conditions, four situations, frozen context snapshots, three output fields, model/settings, and legacy coder.
- **Local validation reported:** 85 Python regression tests passed; 168/168 MOCK decisions completed.
- **REAL pilot reported:** 56/56 decisions, 28 matched P0/P1 pairs (28 per arm), 116 successful API requests, 0 failed decisions. Estimated API cost: approximately US$0.024 (provider billing is authoritative).
- **Legacy interpretation coder:** P0 = 5 negative / 23 neutral; P1 = 0 negative / 28 neutral.
- **Interpretation:** This is evidence that *framing affected the observed labels*, not that P1 improved human fidelity. A neutral label can conceal a response that contains both a benign explanation and a threat interpretation. A nonsocial printer answer still referred to prior social rejection under P1.

## v0.4 — Temporal-context ablation

- **Variable:** T1 = event described as occurring **yesterday**; T2 = otherwise matched event described as occurring **six months ago**.
- **Controls:** P0 framing only; six memory-bearing conditions × two time anchors × four situations = 48 decisions, plus four no-memory controls = **52 decisions per repeat**. The no-context baseline was not duplicated into artificial temporal variants.
- **Local validation reported:** 85 Python tests passed; browser/UI MOCK smoke passed; 156/156 decisions in a three-repeat MOCK batch, with 72 temporal pairs.
- **REAL pilot reported:** 52/52 decisions, 24 T1/T2 pairs plus four no-memory controls, 13 snapshots, 112 successful API requests and no retries. Estimated API cost: approximately US$0.0225.
- **Model provenance caveat:** the local report says the requested model identifier was `deepseek-flash` while the response identifier was `deepseek-chat`. The actual serving-model equivalence should be checked before cross-run conclusions.
- **Legacy-coder descriptive results (negative-memory conditions only, n=12 per time arm):**

| Descriptive metric | T1: yesterday | T2: six months ago |
| --- | ---: | ---: |
| Negative interpretation labels | 2/12 | 2/12 |
| Neutral interpretation labels | 10/12 | 10/12 |
| Coder-marked explicit memory references | 7/12 | 3/12 |
| Memory-related spillover in nonsocial S4 | 2/3 | 0/3 |

These are *single-run, tiny-cell observations*. One T1 response with a clear reference to the past was reportedly missed by the memory-reference coder. A distant-memory answer sometimes retained stronger social suspicion or an avoidance action: the result is **not** simple monotonically fading negative affect.

The observed shift from concrete episodic wording to generalized phrasing may reflect the model's interpretation of a textual time cue. It **does not establish** actual autobiographical consolidation, human-like fading affect, causal psychological state formation, or robust improvement in context specificity.

## Measurement problem identified across both versions

The existing mutually exclusive `positive / neutral / negative / unclear` interpretation coder frequently maps **mixed attributions** (e.g. “possibly rejected, but there may be an innocuous explanation”) to `neutral`. This compresses precisely the variation the study intends to measure.

**Recommended next step (evaluation-first):** re-code existing saved responses with separate, pre-specified dimensions, without generating new agent outputs yet:

1. Threat attribution / suspicion.
2. Benign attribution / alternative explanation.
3. Memory intrusion or inappropriate cross-situation transfer.
4. Behavioral withdrawal / avoidance.

Use a blinded human-reviewed subset, clear coding definitions, and disagreement checks before regarding a new coder as better. Keep legacy labels for comparison and document any changes to coding rules. Do not optimize prompts against an unstable scoring procedure.

## Human-reference status and limitations

- The human Calm Thinking dataset previously explored contains repeated human recognition-similarity ratings (1–4) over ambiguous scenarios. These are **not** directly interchangeable with EchoMind's open-ended `interpretation / speech / action` outputs.
- The exploratory dataset has 3,259 observation rows from 1,524 participants across sessions. These are repeated observations, **not** 3,259 independent humans.
- A credible human-fidelity test requires matching scenarios, task instructions, response scale, human reference distributions, and a justified comparison metric. None of the v0.3/v0.4 pilots provides that matched human ground truth.
- Model repeats are not independent human participants. Uncertainty estimates and held-out scenarios are necessary before generalization claims.
- The scenarios, injected memories, prompts and coder can induce demand characteristics; cross-scenario carryover should be assessed rather than assumed.

## Reproduction and publication boundaries

- The **local isolated** experiments have protocol IDs `prompt_framing_v03` and `temporal_context_v04`. The local v0.3 and v0.4 databases are intentionally separate from the historical EchoMind database.
- The present GitHub revision contains this **progress note only**, not the isolated v0.3/v0.4 implementation, raw prompts, full paired answers, or SQLite files. A separate, reviewed code synchronization is required for reproduction.
- No API keys, private `.env` files, individual-level human data, blind-review keys, or raw experiment databases should be committed. Verify data reuse rights before publishing third-party datasets.
- Before a paper claim: check protocol reproducibility, verify model identifiers and configuration, preregister or freeze primary endpoints, use adequate repeats, and evaluate on matched **human** ground truth with held-out situations.

## Immediate next milestone

**Evaluation v0.5:** develop a multi-axis measurement rubric, audit it on existing v0.3/v0.4 responses, then choose the next *single* injection change based on measured shortcomings. Human alignment—not coder label frequency—is the criterion for selecting the eventual best method.
