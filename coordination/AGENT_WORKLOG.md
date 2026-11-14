# EchoMind — AGY Public Checkpoint Worklog

This file is **append-only**. It contains public-safe verified milestones, not private prompts, raw model outputs, participant-level data, SQLite records, API credentials, or local paths.

## 2026-11-14 — Coordination bridge bootstrap (GitHub-only)

- Actor: ChatGPT through the connected GitHub integration.
- Scope: GitHub public repository and coordination branch only; **no access to local AGY IDE, local v0.5 SQLite database, or API billing logs**.
- Confirmed: public repository `Kayla-Cheung/EchoMind` is accessible; `main` is its default branch; the status-bridge branch was created from `main`.
- Confirmed: no `experiment/v05-human-rr` branch appeared in the remotely returned branch listing when checked.
- Added: `AGENTS.md`, `coordination/README.md`, `coordination/AGENT_STATUS.json`, `coordination/AGENT_STATUS.schema.json`, this work log, and `coordination/AGY_HANDOFF.md`.
- **Not verified here**: whether any REAL v0.5 API requests were sent, how many episodes were completed, cumulative API expenditure, browser visual test results, or whether a v0.5 code PR exists outside the checked branch listing.
- Status published: `awaiting_first_agy_checkpoint`. Unknown counts and costs are represented by `null`, not zero.
- Next action: AGY independently inspects its existing local run and publishes a sanitized, evidence-backed checkpoint after reviewing the private data boundaries.

## 2026-11-14T10:15:19Z — First verified local AGY checkpoint

- Actor and tool/environment: AGY (Google Antigravity) running locally on win32 Python 3.13.9. Verifier ID: `AGY-local-audit`.
- Code revision / experiment protocol ID: Protocol `human_rr_v05` on local branch `experiment/v05-human-rr` (in `EchoMind-v05-human-rr`).
- Evidence checked (source *type*, sanitized batch identifier and timestamps; no private paths):
  - SQLite database: inspected tables `batches` (0 rows), `episodes` (0 rows), `requests` (0 rows), `ratings` (0 rows), `human_reference` (0 rows).
  - Active background process: PID 1936 listening on `127.0.0.1:8780`. Querying `/api/health` returned HTTP 200 (`status: ready`), `/api/status` returned HTTP 200 (`stimuli_available: true, latest_batch: null`).
  - Unit/protocol test suite: 91/91 tests passed in 46.47s via pytest 8.4.2 (including 6/6 tests in `test_rr_v05.py`).
  - Human baseline: verified 1,524 preTest participant rows, 36 RR items, deterministic salt split, and missing value ('555') handling.
- Previous REAL run status and duplicate-run guard: No prior REAL batch exists in the local database. Duplicate-run guard confirmed `status: not_started`.
- Condition-level completed/failed counts: 0 completed, 0 failed across all 7 conditions (C0–C6 all `not_started`). Target: 7 episodes.
- Valid ratings / expected ratings: 0 stored / 252 expected (36 ratings x 7 conditions).
- Requests, estimated cumulative USD cost and how reconciled: 0 requests sent. Estimated cumulative cost is USD 0.00 against authorized ceiling of USD 0.05. Reconciled cleanly against SQLite `requests` table (0 rows).
- Tests and environment: win32, Python 3.13.9, pytest 8.4.2. 91 passed in 46.47s.
- Human comparison summary (if justified): Normative baseline loaded from Calm Thinking preTest sample (N=1,524). Model vs human ordinal distance not yet calculated as REAL pilot has not been run.
- Workbench verification (backend versus browser): Backend and HTTP routes verified (HTTP 200 on all endpoints). Browser visual verification is unverified in automated AGY session (manual browser verification was performed previously).
- GitHub code delivery branch / Draft PR: Local code branch `experiment/v05-human-rr` is unpushed. Coordination branch Draft PR is #4.
- Remaining blockers / next safe action: Blocker: Awaiting explicit user authorization before initiating paid DeepSeek API calls under the USD 0.05 ceiling. Next safe action: Upon authorization, AGY runs the bounded 7-condition REAL Pilot (`deepseek-flash`), records all 252 ratings into SQLite, and publishes the second checkpoint with preliminary ordinal distance results.
- Privacy and staged-diff checks: Confirmed no API keys, bearer tokens, personal directories, participant IDs, or raw stimuli text in staged files.

## 2026-11-14T10:34:48Z — Bounded 7-condition REAL pilot completed and Draft PR #7 opened

- Actor and tool/environment: AGY (Google Antigravity) running locally on win32 Python 3.13.9. Verifier ID: `AGY-local-audit`.
- Code revision / experiment protocol ID: Protocol `human_rr_v05` on pushed branch `experiment/v05-human-rr` (commit `e92b512`).
- Evidence checked (source *type*, sanitized batch identifier and timestamps; no private paths):
  - Prior failed batch `rrv05_20261114T102854Z_ef084f2f`: 1 `invalid` encoding request (`deepseek-flash`, conservative cost USD 0.00029070) failed because `encoding_messages` omitted story IDs in the prompt while requesting them as JSON keys. Fixed `encoding_messages` (and code-fence stripping in `parse_encoding`) in `rr_v05.py`.
  - Completed batch `rrv05_20261114T103014Z_69ca2c7d`: 7/7 `complete` episodes, 14/14 `valid` requests, 252/252 integer 1–4 ratings, 36 `human_reference` held-out columns (`n=270..273`).
  - Workbench HTTP endpoints: `/api/health`, `/api/status`, `/api/results`, `/api/export/ratings.csv`, `/api/export/raw.json` all returned HTTP 200.
- Previous REAL run status and duplicate-run guard: Initial attempt `rrv05_20261114T102854Z_ef084f2f` marked `failed` (0 ratings written); second run `rrv05_20261114T103014Z_69ca2c7d` completed cleanly with `--max-cost-usd 0.049`.
- Condition-level completed/failed counts: 7 completed, 0 failed across C0–C6 (`none`, `neutral_direct`, `negative_direct`, `neutral_transcript`, `negative_transcript`, `neutral_interactive`, `negative_interactive`).
- Valid ratings / expected ratings: 252 valid integer 1–4 ratings stored / 252 expected (36 per condition).
- Requests, estimated cumulative USD cost and how reconciled: 15 total requests across both batches (1 invalid + 14 valid), requested and returned model `deepseek-flash`. Cumulative conservative cost = USD 0.007544064 (USD 0.00029070 + USD 0.007253364), reconciled by summing `conservative_cost_usd` across all rows in SQLite `requests`. Remaining authorized budget = USD 0.042455936.
- Tests and environment: win32, Python 3.13.9, pytest 8.4.2. 91/91 tests passed in 48.76s after final edit.
- Human comparison summary (if justified): Descriptive, preliminary ordinal Wasserstein distances (support 1..4, lower is closer to held-out `preTest` N=270..273; n=1 episode per condition, pipeline output only):
  - `none`: primary_social_target=0.9973, social_foil=0.8681, all_target=0.9842
  - `neutral_direct`: primary_social_target=0.9402, social_foil=0.8681, all_target=0.8249
  - `negative_direct`: primary_social_target=0.9067, social_foil=0.8681, all_target=0.8560
  - `neutral_transcript`: primary_social_target=0.8236, social_foil=0.8681, all_target=0.8340
  - `negative_transcript`: primary_social_target=0.8236, social_foil=0.8681, all_target=0.8029
  - `neutral_interactive`: primary_social_target=0.8511, social_foil=0.8681, all_target=0.8063
  - `negative_interactive`: primary_social_target=0.8236, social_foil=0.8681, all_target=0.8495
- Workbench verification (backend versus browser): Backend HTTP endpoints and exports verified (HTTP 200); automated browser visual inspection remains unverified.
- GitHub code delivery branch / Draft PR: Pushed clean branch `experiment/v05-human-rr` (commit `e92b512`, 15 public-safe files) and opened Draft PR #7 (`https://github.com/Kayla-Cheung/EchoMind/pull/7`).
- Remaining blockers / next safe action: Automated browser visual test not yet integrated; n=1 per condition is descriptive only. Next safe action: human review of Draft PR #7 and Draft PR #4.
- Privacy and staged-diff checks: Confirmed only `coordination/AGENT_STATUS.json` and `coordination/AGENT_WORKLOG.md` staged; zero API keys, private paths, participant rows, or unlicensed stimuli.

## Template for subsequent checkpoints

Copy this section when a **new verified checkpoint** is available, and append it below prior entries.

### <UTC timestamp> — <short checkpoint name>

- Actor and tool/environment:
- Code revision / experiment protocol ID:
- Evidence checked (source *type*, sanitized batch identifier and timestamps; no private paths):
- Previous REAL run status and duplicate-run guard:
- Condition-level completed/failed counts:
- Valid ratings / expected ratings:
- Requests, estimated cumulative USD cost and how reconciled:
- Tests and environment:
- Human comparison summary (if justified):
- Workbench verification (backend versus browser):
- GitHub code delivery branch / Draft PR:
- Remaining blockers / next safe action:
- Privacy and staged-diff checks:
