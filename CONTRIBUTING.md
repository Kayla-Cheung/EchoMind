# Contributing to EchoMind

Use Python 3.11. The maintained workbench and public checks need no third-party
Python packages. The separate analysis environment is described in
`human-analysis/environment.yml`; historical RR tests additionally require private
fixtures and, in some cases, pytest and a permitted tokenizer artifact.

## A reviewable change

1. Inspect the working tree and select the experiment/version being changed.
2. State the concrete problem and expected resulting behavior. Separate software
   maintenance from changes to hypotheses, stimuli, prompts or evaluation.
3. Implement a focused change. For a new scientific protocol, create a new version
   and index it in `configs/experiments.json`; retain the historical implementation.
4. Run `python scripts/run_checks.py --snapshots`. On a normal development host,
   also run it with `--http`. The public RR smoke checks use synthetic fixtures;
   passing them is not a replication of the original human task.
5. Inspect `git diff --check`, `git diff`, and the files selected for commit.
   Include the problem, final behavior, checks performed and material limitations
   in the pull request description. A proposal and a completed experiment need
   different evidence descriptions.

## New experiments

Record the experimental unit and dependencies; primary comparison and endpoints;
memory/stimulus/prompt/scoring versions; requested and returned model identity;
sampling settings; attempted, successful, failed and missing observations; retries;
budget and stopping rules; human reference and development/test split; and the
analysis command and artifact provenance. Keep changes made after inspecting a
test set explicit. No arbitrary sample size is prescribed by repository tooling.

Start with local checks and an inspectable frozen configuration. Real model calls
follow the existing protocol's execution/budget controls and the user's authorized
scope. Re-running a historical script can incur costs and is not a setup step.

## Data and publication

Use the locations and restrictions in [data-access.md](docs/data-access.md).
Do not attach participant-level data or restricted stimuli to issues or PRs.
Publish only permitted reviewed artifacts. No repository-wide license has yet been
selected; do not assume another study's license applies to EchoMind or its inputs.
