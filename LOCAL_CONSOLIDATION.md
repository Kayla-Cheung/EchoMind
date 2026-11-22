# Local EchoMind consolidation — 2026-11-22

The repository brings the existing desktop demo, research notes, analysis workspace,
and independent experiment implementations into one checkout. The original source
directories are preserved. Independent protocols keep their own source trees and
databases; copying a version here does not turn it into a new experiment or validate
its findings.

| Directory | Source and purpose |
| --- | --- |
| Repository root | Existing desktop EchoMind demo and its uncommitted local improvements |
| `docs/research/notes/` | Research memo branch, including the 2026-11-15 note |
| `human-analysis/` | Desktop EchoMind-analysis notebook, codebook and environment |
| `experiments/v03-prompt-framing/` | Independent v0.3 prompt-framing source snapshot |
| `experiments/v04-temporal-context/` | Independent v0.4 temporal-context source snapshot |
| `experiments/v05-human-rr/` | Independent v0.5 human Recognition Ratings source snapshot |
| `experiments/rr-isolation/` | RR-ISOLATION-001 workbench and runner source snapshot |

`LOCAL_CONSOLIDATION_MANIFEST.json` records source paths and SHA-256 hashes of the
copied experiment source files. Snapshots retain their existing filenames and imports
so different `rr_v05.py` or `acquisition.py` implementations cannot overwrite each
other. Run commands from the selected version's directory. Historical launch and
data-acquisition helpers may reference their original Windows paths; inspect those
paths before using them on another computer.

## Data and public synchronization

Local experiment data, private inputs/exports and the analysis CSV are copied into
their corresponding version directories, where available. They are excluded from
Git. Databases from different protocols are not combined, rewritten or re-scored.
Downloaded papers and source backups remain local. The older SOS project is a
pre-migration archive and is not overlaid on EchoMind.

GitHub receives source, documentation, aggregate analysis materials and the notebook
with saved outputs cleared. It does not receive individual-level human data, private
inputs/exports, raw experiment databases, paper PDFs, credentials or local logs.
The tracked scenario and RR source-manifest JSON files are configuration/provenance,
not participant response records. Fresh clones must obtain permitted external data
separately; this synchronization does not redistribute it.

## Verification

The main demo's Python suite was attempted before consolidation: 76 of 80 executed
tests passed; four HTTP tests failed and two HTTP test classes could not initialize.
A direct localhost request reproduced Windows socket error 10013 in the execution
environment. These HTTP checks remain unverified here; they are not reported as
passing. Offline logic checks and the independent snapshots are checked separately
in the synchronization verification record.

No paid model calls or new human/agent experiments were run for this consolidation.
