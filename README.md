# EchoMind

Controlled experiments on how supplied memories/context change LLM responses to
ambiguous situations, with a developing human-reference evaluation pipeline.

**Research status:** exploratory pilots. EchoMind has not established that its
agents reproduce matched human individuals, possess human psychological states,
or predict clinical outcomes. Improving person-specific prediction on unseen
tasks is a research goal, not a completed result.

## Start here

For file locations, existing-data audits, new study design and daily operations,
start with [WORKFLOW_SOP.md](WORKFLOW_SOP.md). Reusable protocol, analysis plan,
decision log and run-manifest templates are in [templates/](templates/).

Use Python **3.11** from this checkout's root. The demo, repository checks and
public protocol smoke checks use the Python standard library; no API key,
participant dataset or package installation is needed for these commands.

```sh
python scripts/run_checks.py --snapshots
```

This checks public files and snapshot integrity, runs the core logic tests, and
checks each version in a separate process. It prints the exact localhost tests
excluded from this default run. To include those integration tests on a machine
that permits localhost connections:

```sh
python scripts/run_checks.py --snapshots --http
```

An unavailable localhost connection fails the explicitly requested HTTP run.
Synthetic smoke checks verify software behavior; they are not research evidence.

Open the current workbench without model calls:

```sh
python launch_demo.py --offline
```

The launcher opens `http://127.0.0.1:8769/` and uses this checkout's own database.
See [WORKBENCH_GUIDE.md](WORKBENCH_GUIDE.md) for the detailed historical interface
guide and [reproducibility.md](docs/reproducibility.md) for scope and limitations.

## Experiments and evidence

Review existing local evidence without model calls:

```sh
python data_audit.py
```

This opens `http://127.0.0.1:8770/`. The independent review service inventories
SQLite evidence in this checkout (use `--base ..` to inspect surrounding legacy copies),
identifies repeated trial IDs and conflicting payloads, and supports separate,
append-only review decisions. Source databases are opened with SQLite read-only
connections. See [docs/data-audit-workbench.md](docs/data-audit-workbench.md).

| Location | Question / role | Current boundary |
| --- | --- | --- |
| Root Python modules and `web/` | Historical workbench; context acquisition, source and format controls | Exploratory; MOCK and real records must remain separate |
| `experiments/v03-prompt-framing/` | Original versus everyday-response framing | Preserved source snapshot; framing-dependent labels do not establish human fidelity |
| `experiments/v04-temporal-context/` | Yesterday versus six months ago | Textual time cues; not elapsed-time memory consolidation |
| `experiments/v05-human-rr/` | Human-referenced 1–4 Recognition Ratings | Private stimuli/reference required; similarity is not emotion intensity |
| `experiments/rr-isolation/` | Batched versus isolated stories | Descriptive pilot, two ratings per item/arm/condition; no consistent improvement established |
| `human-analysis/` | Human data inspection and codebook | Obtain permitted source data separately; notebook outputs are cleared |

[configs/experiments.json](configs/experiments.json) is the machine-readable index.
Run commands from the intended version directory: identically named modules in
different snapshots are not interchangeable. Historical snapshots remain frozen;
new research changes belong in an explicitly versioned implementation.

The [2026-11-08 progress note](RESEARCH_PROGRESS_2026-11-08.md) is a historical
record. The [consolidation record](LOCAL_CONSOLIDATION.md) documents the later
arrival of experiment source snapshots. Neither is a new replication.

## Data and reproducibility

Public Git contains code, protocols, provenance metadata and cleared notebooks.
Participant records, original restricted stimuli, raw model traces, SQLite
databases, credentials and local exports are excluded. A fresh clone can run the
public checks but cannot reproduce all historical numerical results without the
permitted private inputs. See [data-access.md](docs/data-access.md).

Before a new real experiment, freeze the protocol, item set, prompts, scoring,
model/settings and budget; preserve raw responses and failures. Prices and model
aliases in old snapshots require fresh verification. The check runner neither
starts real experiments nor approves their execution.

## Development

- [CONTRIBUTING.md](CONTRIBUTING.md): changes, checks and review expectations.
- [AGENTS.md](AGENTS.md): instructions for automated coding contributors.
- [Repository comparison and refinement](docs/repository-review-2026-11-23.md):
  comparison with established study repositories and remaining gaps.
- [Previous verification](SYNC_VERIFICATION_2026-11-22.md): dated historical results.

There is currently no project-wide license grant in this checkout. Third-party
data, stimuli and model terms remain separate; public visibility does not imply
permission to redistribute them. No paper DOI or release citation is claimed.
