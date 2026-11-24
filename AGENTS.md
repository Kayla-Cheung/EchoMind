# Working on EchoMind

## Scope

This checkout is the consolidated EchoMind repository. Read `README.md`,
`configs/experiments.json`, and the protocol for the version being changed.
Do not confuse it with a surrounding legacy working tree or another desktop copy.

## Research invariants

- Preserve raw inputs, responses, failures, logs and human data. Analysis writes
  new derived outputs, never rewrites source evidence.
- `experiments/` contains historical snapshots. Preserve their contents and
  `configs/snapshot-integrity.json`. Make a new version for scientific changes;
  do not silently regenerate the integrity manifest to accept a mismatch.
- Separate MOCK/fake transport checks from real observations. Model repeats are
  not independent humans; multiple branches from one snapshot are dependent.
- Keep Recognition Ratings separate from free-response interpretation/speech/
  action coding. Do not describe semantic similarity as emotion intensity.
- The matched-person human validation goal remains unproven. Reformatting code
  does not validate a psychological construct or improve human fidelity.
- Formal new research materials use English. Preserve historical materials in
  their original language and record any translation as a protocol change.

## Changes and verification

- Inspect `git status` first; preserve unrelated work. Use focused changes and
  inspect the final diff. Keep independently versioned modules in separate processes.
- Run `python scripts/run_checks.py --snapshots`. Add `--http` when localhost is
  available; report excluded checks and failures accurately. CI requests HTTP.
- Add tests for substantive logic changes, particularly parsing, denominators,
  missing data, protocol boundaries and costs. Avoid tests of mere wording.
- No model calls, dataset downloads, historical reruns, publication, or remote
  changes are implied by a repository-maintenance task. Follow the user's actual
  authorization; do not add repeated approval requests for already authorized work.
- Never commit `.env`, participant rows, restricted item text, private split
  salts, raw databases, raw model exports or credentials. Keep notebook outputs
  cleared. The public-file checker is a guard, not a substitute for diff review.
- Historical prices/model aliases and machine-specific launch scripts are not
  portable current configuration. Do not silently change them inside snapshots.
