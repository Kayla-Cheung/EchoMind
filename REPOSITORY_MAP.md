# EchoMind Repository Map & Sync Policy

This map defines the relative-path structure, single-source-of-truth ownership, and privacy boundaries across local workspaces and `Kayla-Cheung/EchoMind`.

## Active Branches & Draft PRs

| Branch | PR | Role | Notes |
| :--- | :--- | :--- | :--- |
| `main` | — | Stable public baseline | Default branch |
| `experiment/v05-human-rr` | Draft PR #7 | v0.5 human-referenced Recognition Ratings protocol, runner, workbench, tests | 15 public-safe files |
| `coordination/agent-status-bridge-v1-20261114` | Draft PR #4 | Public-safe AGY status bridge & append-only checkpoint worklog | `AGENTS.md`, `coordination/*` |
| `docs/local-remote-structure-001` | Draft PR | Repository map, research memo template, read-only preflight check | Issue #9 deliverables |
| `docs/related-work-structure-20261022` | Open PR #1 | Legacy `echomind/` package refactor | Evaluate separately; do not auto-merge |

## Single-Source-of-Truth & Privacy Classification

| Category | Relative Paths | Owner | Public GitHub Policy |
| :--- | :--- | :--- | :--- |
| **Versioned v0.5 source** | `rr_v05.py`, `rr_workbench.py`, `run_rr_real.py`, `launch_rr_v05.py`, `model_client.py`, `web/rr_v05.*`, `Open_EchoMind_v05.cmd`, `start_rr_v05.ps1` | `experiment/v05-human-rr` (PR #7) | Tracked & PR-reviewed |
| **Public protocol & tests** | `HUMAN_RR_V05_PROTOCOL.md`, `data/rr_v05_source_manifest.json`, `tests/test_rr_v05.py` | `experiment/v05-human-rr` (PR #7) | Tracked & PR-reviewed (`test_rr_v05.py` skips private-stimuli tests when absent) |
| **Public research memo** | `docs/research/RESEARCH_MEMO.md` | Owner-authored | Template only until owner writes & approves claims |
| **Public-safe logs & status** | `coordination/AGENT_STATUS.json`, `coordination/AGENT_WORKLOG.md`, `WORKLOG_V05.md` | `coordination/` (PR #4) & `WORKLOG_V05.md` (PR #7) | Sanitized milestones only; no local paths, raw outputs, or keys |
| **Private stimuli / unclear license** | `private_inputs/calm_rr_v42.json`, `papers/*` | Local-only | Never push (gitignored) |
| **Private SQLite & raw responses** | `data/human-rr-v05.sqlite3`, `data/pilot.sqlite3`, `private_exports/*` | Local-only | Never push (gitignored) |
| **Human participant records** | `data/human_benchmarks/*.sav`, `*.spv`, `rr.csv` | Local-only | Never push |
| **Secrets & split salts** | `.env`, `private_inputs/split_salt.txt` | Local-only | Never push (`.env.example` only) |
| **Generated intermediates** | `__pycache__/`, `.pytest_cache/`, `*.log`, `private_exports/pytest-*` | Local-only | Gitignored |

## Sync Rules

1. Never run `git add -A` on a dirty Desktop or historical experiment working tree.
2. Keep historical v0.3/v0.4 workspaces immutable; do not overwrite source trees to force identical layouts.
3. Run `python scripts/preflight_sync_check.py` (read-only) before staging or opening any PR.
