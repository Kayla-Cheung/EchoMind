# Research evaluation routes

## Current status

The repository preserves multiple evaluation routes without declaring a Human Benchmark selected.

**MindTrails is a candidate, not a decision.** Before any MindTrails material is treated as a benchmark, its exact task, license/terms, accessible data, scoring procedure, population, and construct match must be verified from the owning source. A related psychological task or paper is not automatically a reusable dataset, and aggregate published results are not participant-level ground truth.

## Route A: selective-choice psychological scenarios

Use matched ambiguous scenarios with pre-specified response options when the source task and scoring can be reproduced faithfully. Required checks include:

- task and construct alignment with EchoMind's claim;
- matched scenario wording and response scales;
- provenance, license, inclusion/exclusion rules, and population metadata;
- a frozen scoring rule before model results are inspected; and
- separate reporting of model trials and human participants.

This route can provide a cleaner comparison target, but only when the task is truly comparable. It must not be presented as a human benchmark merely because it is psychology-related.

## Route B: free response plus post-hoc annotation

Keep the Demo's natural response path, including `interpretation`, optional `speech`, and concrete `action`, then annotate exported answers after generation.

Recommended controls:

- blind annotators to memory/source condition where feasible;
- version the codebook and annotation form;
- preserve raw public responses and never overwrite model coding with human labels;
- measure inter-rater agreement and retain disagreements/uncertainty;
- separate interpretation, affect, memory linkage, and action dimensions; and
- report missing, invalid, and uncodeable outputs in denominators.

The multi-axis route in `memory-source-v2` is designed for this direction. It is exploratory until independently annotated and validated.

## Decision gate

Do not name a formal Human Benchmark until the exact source materials and permissions are verified, the comparison task is matched, and the scoring/annotation plan is frozen. Until then, use terms such as *candidate dataset*, *candidate task*, or *external reference*.
