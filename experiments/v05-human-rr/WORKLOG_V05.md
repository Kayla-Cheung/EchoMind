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

### Pending verification entries

- Static/unit/protocol test result: pending.
- Prompt/UI preview result: pending.
- REAL batch ID, returned model, usage, cost, and primary distance: pending.
- Secret scan, diff review, commit, push, and draft PR: pending.

### Local website access repair

- Found the prior task-owned Python process listening on 8780 while local connections timed out, including a direct request made outside the restricted execution environment.
- Stopped only the verified stale v0.5 process and restarted this workbench as a detached background process with absolute database and stimulus paths.
- Added `launch_rr_v05.py`, `Open_EchoMind_v05.cmd`, and a workspace-specific `/api/health` endpoint. Updated `start_rr_v05.ps1` to wait for readiness, reuse a healthy service, and leave unrelated port owners untouched. Local service logs stay in the git-ignored `private_exports/` directory.
- Verified HTTP 200 for the home page, JavaScript, CSS, health, status, measurement, and results routes in a separate command session after startup. Measurement returned 9 scenarios and 36 interpretations. Repeated startup reused the same process.
- Verified the actual in-app browser shows `Local data ready`, the measurement page, and the result page's correct empty state. Kept the working browser tab open.
- This repair made no model API calls and created no experiment batch. REAL pilot, publication audit, and GitHub draft PR remain pending.
