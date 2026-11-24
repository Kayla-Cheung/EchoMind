# Reproducing software checks and research results

## Public checks

From the repository root, with Python 3.11:

```sh
python scripts/run_checks.py --snapshots
```

The runner executes the public-file audit, core unit tests, the v0.3/v0.4
acquisition tests and public RR smoke tests in separate processes. RR smoke tests
create clearly synthetic stories and ratings in a temporary directory. They test
phase separation, response validation, experiment coverage and known ordinal
distance cases without reading the historical stimuli, human rows or databases.
The two RR versions are imported in separate interpreters to prevent collisions.

Default core checks explicitly exclude localhost integration tests and print their
IDs. To request them, use:

```sh
python scripts/run_checks.py --snapshots --http
```

The runner first checks a real loopback request; inability to make that request is
a failure of this requested scope, not a pass. CI uses this command on Linux and
Windows. Browser smoke checks are separate and are not included; their historical
Node/browser requirements are documented in the workbench guide.

## What a fresh clone cannot reproduce

- Historical real model outputs: API access, reviewed execution configuration,
  current model availability and a budget are needed to collect new observations.
  Provider updates can prevent identical generations.
- Historical human-reference distances: permitted original materials, participant
  data, the original private split information and the correct saved model batch
  are required. A new split does not reproduce the old test set.
- Full legacy RR test suites: some tests read restricted stimuli, private gate
  records or a tokenizer ZIP at original machine-specific paths. They are not
  silently replaced by, or counted as, the public synthetic checks.
- Matched-human individual validation: it has not been completed. Item-wise
  population marginals alone cannot establish person-specific prediction.

Do not run `run_real.py`, `run_rr_real.py`, approval helpers or old data-acquisition
scripts as verification commands. Read their version-specific protocol first.

## Provenance and isolation

`LOCAL_CONSOLIDATION_MANIFEST.json` retains the original source locations and raw
byte SHA-256 values at consolidation. Those values can depend on Windows line
endings. `configs/snapshot-integrity.json` separately records SHA-256 after CRLF
is normalized to LF, so the same historical text can be checked on Linux and
Windows. It records integrity, not scientific validity. Neither file is an
experiment configuration or a replacement for the original protocol hashes.

The checker rejects missing/extra snapshot files, changed snapshot text, private
public-tree paths, obvious credential patterns and saved notebook output. It checks
tracked plus non-ignored untracked files, so staged ignored files are included.
Review the actual diff as well: no heuristic can certify every file as safe.

The [2026-11-24 synchronization record](sync-2026-11-24.md) documents the explicit
integrity migration for upstream privacy/security sanitization. The current index
tracks that sanitized public snapshot tree; the original consolidation manifest
retains its historical meaning.

For an analysis result, record the source commit, protocol/configuration hash,
input fingerprints, model batch and source type, scoring version, exact item
subset, failure/missing-data rules and command. Output to a new private/derived
location. Software test success is independent of human-behavioral fidelity.
