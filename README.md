# EchoMind Demo

EchoMind is a local, standard-library Python research demo for testing how controlled context or memory injection changes an LLM's public response to ambiguous situations. The application keeps the existing three-part output contract—`interpretation`, `speech`, and `action`—and stores the visible answer, coding result, prompt metadata, and audit fields in a local SQLite database.

This repository contains program code and non-sensitive protocol documentation only. It intentionally does **not** contain API keys, `.env` files, local SQLite databases, model responses, experiment logs, screenshots, or exported participant/model records.

## Run locally

Requirements: Python 3.10+; no third-party package installation is required.

Safe offline start (recommended first run):

```powershell
python launch_demo.py --offline
```

Then open <http://127.0.0.1:8769/>. Offline mode blocks credential loading and live provider calls; MOCK output is only a workflow check and is not model or human evidence.

To enable live providers, copy `.env.example` to `.env`, add keys locally, and run:

```powershell
python launch_demo.py
```

The UI still starts with non-live choices. Review the request preview, model, call counts, and budget before authorizing any real run. Never commit `.env` or anything under `data/` other than the included scenario fixture.

Run the offline test suite:

```powershell
$env:ECHOMIND_OFFLINE = "1"
python -m unittest discover -s tests -v
```

## Architecture

- `server.py` and `launch_demo.py`: repository-level entry points and workspace-safe launcher.
- `echomind/server.py`: local HTTP API and static UI routing.
- `echomind/runner.py`: plans isolated calls, separates role generation from coding, and persists job state.
- `echomind/acquisition.py`: the existing context-injection protocol (`memory_acquisition_v02`) with frozen snapshots and `interpretation` / `speech` / `action` output.
- `echomind/measurement.py`: source × valence measurement route with multi-axis post-hoc coding.
- `echomind/model_client.py`: provider adapters; only user-visible final content enters behavioral coding.
- `echomind/storage.py`: local SQLite persistence. Databases remain untracked.
- `web/`: the local workbench UI.
- `docs/`: protocol boundaries and research-design notes.

The Demo does not establish private mental states, human psychological fidelity, or causal mechanisms. MOCK runs are functional checks. Live model runs remain model-output experiments, not human-subject data.

## Research evaluation status

MindTrails remains a **candidate source of task ideas/materials**, not a selected or validated Human Benchmark. The planned evaluation routes remain:

1. matched, psychology-grounded selective-choice scenarios; and
2. free responses followed by blinded, versioned post-hoc annotation.

See [docs/research-evaluation.md](docs/research-evaluation.md) for the decision gates and constraints.

## Security and repository hygiene

The ignore policy excludes `.env*` (except `.env.example`), SQLite/database files, logs, JSONL exports, generated archives, caches, and all local `data/` content except `data/scenarios.json`. Before publishing changes, inspect the staged file list and run a secret scan appropriate to your environment. Treat any previously exposed credential as compromised and rotate it; deleting it from the latest commit is not sufficient.
