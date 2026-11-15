# EchoMind v0.5 Work Log

All times use Asia/Shanghai unless marked UTC.

## 2026-11-14

- Verified the isolated v0.4 source branch and preserved its dirty worktree without modification.
- Created isolated directory `work/EchoMind-v05-human-rr` and branch `experiment/v05-human-rr` from the v0.4 working state.
- Verified local Calm Thinking sources: `measures-v4.2.pdf`, `rr.csv`, and the analysis notebook.
- Verified that the source measure contains nine English scenarios, nine comprehension questions, 36 English interpretations, source order, and the 1–4 similarity scale.
- Verified the local rating table shape: 3,259 rows, 45 columns, 36 RR columns, and 1,524 preTest observations; `555` is handled as missing.
- Licensing finding: the public OSF materials node reports no explicit node license. Full source items and participant-level data remain local and git-ignored.
- Added v0.5 protocol/persistence/cost code, bounded REAL runner, private source loader, local workbench, exports, and protocol tests.
- Pricing source checked: DeepSeek official pricing page, 2026-11-14. `deepseek-flash` was listed as serving DeepSeek-V4.1-Flash-1017; peak cache-miss input USD 0.30/M and peak output USD 1.20/M were used for the guard.

### Verification & REAL Pilot Checkpoint (2026-11-14T10:34:48Z)

- Static/unit/protocol test result: 91/91 tests passed via `pytest` 8.4.2 on win32 Python 3.13.9 (48.76s) after `rr_v05.py` story ID fix.
- Prompt/UI preview result: backend endpoints (`/api/health`, `/api/status`, `/api/results`, `/api/export/ratings.csv`, `/api/export/raw.json`) verified HTTP 200; automated browser visual test remains pending integration into test runner.
- REAL batch ID, returned model, usage, cost, and primary distance:
  - Prior failed attempt `rrv05_20261114T102854Z_ef084f2f`: 1 invalid encoding request (`deepseek-flash`, conservative cost USD 0.00029070).
  - Completed bounded pilot `rrv05_20261114T103014Z_69ca2c7d`: 7/7 complete episodes (C0–C6), 14/14 valid requests (`deepseek-flash`), 252/252 integer 1–4 ratings; cumulative conservative cost USD 0.007544064 across both batches (remaining USD 0.042455936 from USD 0.05 ceiling).
  - Descriptive preliminary `primary_social_target` ordinal Wasserstein distances (`n=1` episode per condition vs. held-out `preTest` N=270..273): `none`=0.9973, `neutral_direct`=0.9402, `negative_direct`=0.9067, `neutral_transcript`=0.8236, `negative_transcript`=0.8236, `neutral_interactive`=0.8511, `negative_interactive`=0.8236.
- Secret scan, diff review, commit, push, and draft PR: clean branch `experiment/v05-human-rr` pushed (commit `e92b512`, 15 public-safe files) and Draft PR #7 opened (`https://github.com/Kayla-Cheung/EchoMind/pull/7`).

### Local website access repair

- Found the prior task-owned Python process listening on 8780 while local connections timed out, including a direct request made outside the restricted execution environment.
- Stopped only the verified stale v0.5 process and restarted this workbench as a detached background process with absolute database and stimulus paths.
- Added `launch_rr_v05.py`, `Open_EchoMind_v05.cmd`, and a workspace-specific `/api/health` endpoint. Updated `start_rr_v05.ps1` to wait for readiness, reuse a healthy service, and leave unrelated port owners untouched. Local service logs stay in the git-ignored `private_exports/` directory.
- Verified HTTP 200 for the home page, JavaScript, CSS, health, status, measurement, and results routes in a separate command session after startup. Measurement returned 9 scenarios and 36 interpretations. Repeated startup reused the same process.
- Verified the actual in-app browser shows `Local data ready`, the measurement page, and the result page's correct empty state. Kept the working browser tab open.
- This repair made no model API calls and created no experiment batch. REAL pilot, publication audit, and GitHub draft PR remain pending.
