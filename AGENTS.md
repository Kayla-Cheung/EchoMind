# AGENTS.md — EchoMind public coordination rules

These instructions govern **public-safe status coordination**, not EchoMind's experimental protocol. Do not treat a GitHub status file as an authorization to run paid experiments or change research parameters.

## Data and source of truth
- The local v0.5 SQLite database, run audit trail, process state, and frozen protocol are the authoritative evidence for experiment progress.
- `coordination/AGENT_STATUS.json` is a **last-published, sanitized snapshot**. It is not a live connection to AGY or proof that a process is still running.
- An initial `null` or `unknown` value is intentional. Never replace it with an estimate or a copied previous claim without verification.
- Keep older v0.3/v0.4 experiments and uncommitted user changes untouched.

## Before changing status
1. Verify the exact project, Git branch, process state and SQLite batch/episode records.
2. Reconcile previously attempted requests and cumulative costs **before** any new paid requests. No paid call is authorized by this coordination file alone.
3. Validate `coordination/AGENT_STATUS.json` against `coordination/AGENT_STATUS.schema.json` if a JSON Schema validator is available; always validate JSON syntax.
4. Update `coordination/AGENT_WORKLOG.md` with factual findings and evidence. Include what remains unknown.
5. Push only a sanitized status checkpoint to the **coordination branch**, independent of experimental code. If that branch is unavailable, create a dedicated coordination PR rather than mixing status into the dirty v0.5 worktree.

## Public repository security
**Never commit or paste** API keys, .env files, cookies, tokens, local personal absolute paths, experiment SQLite databases, private raw model outputs, participant-level human data, blind keys, unlicensed stimuli or source PDFs. Use neutral aliases and aggregate counts. Scan the staged diff before pushing.

The v0.5 protocol's prior user-approved REAL pilot ceiling was USD 0.05 cumulative. **Do not infer remaining budget from this number.** Verify prior attempts and live provider configuration before any expenditure; stop if budget cannot be reconciled.

## Allowed changes in this coordination PR
Additive documentation, status JSON/schema, and sanitized work logs only. Do not modify experimental code, the source dataset, runner, existing tests, or the main README as part of status coordination.

## Human review
Create a Draft PR; do not merge or force-push. Do not invent success claims. Human review is required for code merges, destructive actions, new paid batches, new data publication, or changes to the research design.

See `coordination/AGY_HANDOFF.md` for the first checkpoint procedure.
