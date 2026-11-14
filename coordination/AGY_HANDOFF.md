# AGY handoff — Publish first EchoMind v0.5 checkpoint

## Goal

Use the **existing local v0.5 project** to publish its real current state to GitHub. Do not rebuild the experiment, change study design, run MOCK, or automatically repeat the REAL Pilot.

The public coordination branch is:
`coordination/agent-status-bridge-v1-20261114`

The experiment itself is the existing local `EchoMind-v05-human-rr` checkout on `experiment/v05-human-rr`. Do not modify the original v0.3/v0.4 or Desktop worktrees.

## Strict execution order

1. **Recover, read only:** Verify the local project identity, Git status, any active server or runner process, the v0.5 SQLite database and run-audit records, existing REAL batch IDs/episodes and possible incomplete requests. Distinguish "not started", "partial", "completed", "failed", and "unknown" from durable evidence. Do **not** infer the answer from a terminal statement like "starting pilot".
2. **Reconcile budget, read only:** Check previously attempted DeepSeek requests, stored usage, failed/retried calls and remaining budget. Approved cumulative ceiling was USD 0.05, but no remaining amount is assumed. If reconciliation is impossible, report a blocker and **do not issue another paid request**.
3. **Validate the experiment, read only:** Report existing v0.5 protocol/test evidence and remaining gaps, including the distinction between successful backend HTTP tests and unverified browser visual inspection. Do not claim that 91/91 tests passed now unless that run is backed by local evidence.
4. **Create a sanitized checkpoint:** Update `coordination/AGENT_STATUS.json` using its schema. Replace unknowns only when locally verified. Use `last_updated_utc` as a real UTC ISO-8601 timestamp. Put evidence descriptions in the work log, never in a secret-bearing field. Validate JSON syntax and schema; do not place private local paths in either file.
5. **Append the factual work log:** Add a new checkpoint section to `coordination/AGENT_WORKLOG.md`. Report unexpected failures, unknowns and scope limits accurately.
6. **Stage and inspect only these two files:** the status JSON and work log. Use the GitHub API or a **separate clean worktree for the coordination branch**. Do not checkout this branch into the dirty local v0.5 working tree. Review the staged diff for private data and secrets.
7. **Push status to coordination branch:** Update the existing Draft PR if present. Do not merge, force push, stage unrelated source, or publish raw data.

## Required status semantics

- `null`: not yet verified, **never** interpreted as zero.
- `unknown`: status cannot be established.
- `completed`: backed by a verified successful episode in the local audit database.
- `failed`: backed by a failure record (do not silently retry).
- `blocked`: missing reliable evidence, budget reconciliation or authorization.
- `cumulative_estimated_cost_usd`: the sum for this pilot's actual attempts, including partial/retried requests where billed or conservatively accounted.
- `cost_reconciled`: only `true` if the complete pilot's earlier billable attempts can be reasonably reconciled.
- `completed_episodes`: count of durable completed episodes, at most 7.
- `valid_rr_ratings`: count of stored valid 1–4 RR responses, at most 252.
- `last_verified_by`: non-personal identifier for the verifying agent, e.g. `AGY-local-audit`.

## How to sync using a separate worktree

Use a separate clean worktree or GitHub API so experimental source remains untouched. A possible Git procedure, adapted to local Git configuration:

```bash
git fetch origin
git worktree add --detach <separate-safe-directory> origin/coordination/agent-status-bridge-v1-20261114
# In the new worktree, create a local branch or use GitHub API to write files.
# Stage ONLY coordination/AGENT_STATUS.json coordination/AGENT_WORKLOG.md.
# Review git diff --cached --check and git diff --cached.
# Push to coordination/agent-status-bridge-v1-20261114 only if verified and safe.
```

If the branch moved remotely, fetch and reconcile before updating; no forced push.

## Explicit boundaries

- The public GitHub checkpoint is an **asynchronous status report**, not a live AGY connection.
- Do not expose DEEPSEEK_API_KEY, .env, bearer tokens, user home directory, participant-level Calm Thinking RR rows, private model transcripts, unlicensed stimuli, or private absolute paths.
- Do not start new API calls based on the presence of this status template. Continuing the authorized pilot requires separate verification of the exact existing run and remaining budget.
- With one episode per condition, Human Fidelity claims remain preliminary and descriptive.
- If you cannot access the local DB/processes, publish `blocked` or retain `unknown` and explain the limitation. Never fabricate seven completed episodes.

## Return to the user

Report the public checkpoint link, actual last-updated UTC time, completed conditions, valid ratings, reconciled estimated cost, observed blockers, and explicit next action. Clarify that ChatGPT can now read the **last synced GitHub status**, not the live AGY IDE.
