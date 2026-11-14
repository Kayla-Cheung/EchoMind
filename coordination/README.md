# EchoMind Agent Status Bridge v1

A **GitHub-based, asynchronous checkpoint exchange** between AGY and ChatGPT. It is **not** a live AGY session API, local remote-control bridge, or automatic task executor.

## Files
- [AGENT_STATUS.json](AGENT_STATUS.json): machine-readable **last published** state.
- [AGENT_STATUS.schema.json](AGENT_STATUS.schema.json): JSON Schema for the public checkpoint.
- [AGENT_WORKLOG.md](AGENT_WORKLOG.md): append-only factual, public-safe change log.
- [AGY_HANDOFF.md](AGY_HANDOFF.md): instructions for the first AGY sync.
- [../AGENTS.md](../AGENTS.md): guardrails when agents handle coordination.

## Flow
1. AGY inspects its **local** v0.5 experiment (processes, SQLite, audit and billing).
2. AGY writes a sanitized checkpoint; updates the log with evidence and unknowns.
3. AGY pushes only the coordination files to the dedicated GitHub branch / Draft PR.
4. ChatGPT can fetch these files using the existing GitHub connection and report the **last synced** state to the user.
5. ChatGPT can draft a GitHub issue with the next explicit, limited task. AGY must separately read and execute it. An issue alone does not control AGY.

## Bootstrap / branch rules
Initial branch: `coordination/agent-status-bridge-v1-20261114` (based on `main`). While the Draft PR is open, AGY may push sanitized status updates to this branch (with user authorization). After the bridge is reviewed and merged, continue status changes in separate short-lived checkpoint branches / PRs or an agreed dedicated state branch. Never overwrite `main` directly.

**Important:** The local v0.5 branch `experiment/v05-human-rr` has not been independently verified as pushed to GitHub. The coordinator branch contains **no experiment code**. AGY must not merge its dirty v0.5 worktree into this branch.

## Privacy and validity
This is a public repository. Do not commit secrets, .env, SQLite, private human participant records, raw full prompts/responses, personally identifying paths, or source materials without verified redistribution permission.

An unchanged `last_updated_utc` means no new GitHub checkpoint; it does not mean the local experiment is idle. A value of `null` means unverified, **not zero**. Only a verified, documented local run can change `real_pilot.status` to `completed`.

No automatic API calls or paid experiments are triggered by state changes.
