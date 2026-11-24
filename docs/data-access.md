# Data access and artifact boundaries

| Artifact | Location | Public repository policy |
| --- | --- | --- |
| Researcher-authored workbench scenarios | `data/scenarios.json` | Tracked configuration |
| Source fingerprints and metadata | `experiments/*/data/rr_v05_source_manifest.json` | Tracked provenance; not full stimuli or human responses |
| Original human CSV | `human-analysis/data/raw/rr.csv` | Local only; obtain from the source under its applicable terms |
| Original RR stimulus JSON and private split information | Selected version's `private_inputs/` | Local only; not included in public fixtures |
| Raw model responses, database and run evidence | Selected version's `private_exports/` or ignored `data/` | Local only; retain immutable evidence |
| New analysis outputs | `human-analysis/data/processed/` or `private_exports/` | Local by default; review rights/content before publishing |
| API credentials | Local `.env` or environment | Never tracked; `.env.example` contains names only |
| Notebook | `human-analysis/notebooks/01_data_exploration.ipynb` | Code only; clear outputs and execution counts |

Source discovery/provenance lives in the versioned source manifests and
`human-analysis/materials/Calm_Thinking_Codebook.md`. At consolidation, an explicit
materials license had not been established for the RR source items. Public
availability is not treated as permission to redistribute. This document does
not grant rights to third-party materials or authorize collection from people.

No real participant rows or original task text are needed for the default public
checks. Their synthetic fixtures use invented text and are explicitly unsuitable
as a scientific replacement for the source task.

When permitted private files are available, use the selected version's protocol
and original schema. Preserve the raw CSV; treat `555` and blanks as missing,
distinguish repeated observations from people, and retain the original split for
historical reproduction. The historical human preTest reference was unprimed;
comparison with a primed model does not validate a matched human intervention.

The analysis workspace accepts an explicit source through
`python human-analysis/copy_data.py <path>`. It hashes the source and
copy, accepts an identical existing copy without rewriting it, and refuses to
overwrite different raw data. The notebook reads only the selected checkout's
`human-analysis/data/raw/rr.csv`; it has no machine-specific fallback.
