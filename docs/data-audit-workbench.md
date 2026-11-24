# Existing-data review workbench

Start from the consolidated repository with `python data_audit.py`, or double-click
`start_data_audit_windows.bat`. The outer workspace also has `start_data_review.bat`.
Open `http://127.0.0.1:8770/`. Python 3.10+ and its standard library are sufficient.
The default scan root is the consolidated repository. Use `--base PATH` to change
the scope, `--scan-only` for a saved inventory, or
`--no-browser` to avoid opening a browser. Restart to refresh an inventory.

## Review sequence

1. Choose a database and batch; compare recorded counts with the original frozen
   job/configuration. The inventory gives observed counts, not inferred planned N.
2. Check failures, unfinished work, raw requests, responses and coding. Use table
   search for a batch, trial, episode or condition ID. Raw JSON fields expand in
   the record inspector; every field remains available.
3. Check related snapshot branches or episodes. Never add database totals across
   backup copies. Identical trial IDs/payloads count once in the inventory;
   different payloads under an ID require manual reconciliation.
4. Record a reviewer, proposed inclusion decision and evidence note. New decisions
   append to a separate history; they do not update the original trial or replace
   machine coding. Export the decision history to freeze an analysis decision set.
5. Analyze RR ratings separately from free-response interpretation/action labels.
   Review episodes and requests as well as rating rows. Confirm human-reference
   provenance and split status separately before making human-validation claims.

This is an unblinded evidence review interface, not a blinded coding task. It does
not compute matched-person validity, significance, automated pairing, or a final
analysis sample. It does not recover missing observations by generating answers.

## Preservation and provenance

Source SQLite handles use `mode=ro` and `query_only`. Experiment/provider modules
are not imported. No API keys, model calls or source-schema migrations occur.
The service binds to loopback. Review POSTs require the matching localhost origin.

`private_exports/data-audit/inventory-<id>.json` preserves each scan;
`inventory.json` records the most recent scan and file
fingerprints. `reviews.sqlite3` stores review events separately, linked to the
source path, table, rowid and SHA-256 of the selected row. A changed source row
fails the save check. Exported review history retains all decisions, not just the
latest. SQL triggers reject event updates/deletes; the review store is still local
application state, not a tamper-proof archive. `research_ops.py freeze-reviews`
creates an exclusive decision version and flags changed/unavailable source rows.

Recovered trial-only audit views under `data/local/derived/` are visible but
excluded from the cross-file trial ID/copy counts. They are not new observations
or complete experiment databases. See WORKFLOW_SOP.md for recovery scope.

Each database is read in one transaction; a scan of multiple live databases is
not a globally simultaneous snapshot. File SHA-256 identifies the main file and
does not incorporate an active WAL. Stop experiments before freezing a final audit.
Inventory covers `.sqlite3` and `.db` files, not every JSON/CSV/SPSS export. Those
remain supplementary evidence to inspect separately. Unknown schemas and damaged
databases are reported, rather than silently treated as empty evidence.

The old destructive `clean_mock_data.py` entry point is disabled in the current
workbench and outer workspace. It now prints a read-only inventory. Frozen
historical experiment snapshots keep their original source for provenance.

## Validation

`python -m unittest discover -s tests -p test_data_audit.py -v` checks source
preservation, retained failures, copy/conflict detection, stale review rejection,
review history, table whitelisting and missing-coding denominators. Run the normal
repository check runner for broader checks. Localhost/browser tests depend on the
execution environment's network permissions and must be reported separately.
