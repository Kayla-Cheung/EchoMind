# Synchronization verification — 2026-11-22

This record checks the local consolidation. It does not validate historical research
claims or reproduce paid model experiments.

| Scope | Result |
| --- | --- |
| Main demo: offline logic tests | 76 passed |
| v0.3 snapshot: acquisition tests | 23 passed |
| v0.4 snapshot: acquisition tests | 23 passed |
| v0.5 snapshot: RR protocol tests | 6 passed |
| RR isolation snapshot: existing pytest suite, excluding HTTP route test | 63 passed, 1 deselected |
| Public file audit before research-note merge | 411 files checked; no forbidden data paths or credential-pattern matches |
| Analysis notebook | Saved outputs and execution counts cleared in the copied notebook |

The main demo's full unittest attempt ran 80 tests with four failures and two test
class initialization errors. The affected checks use localhost HTTP. A separate
direct request to `127.0.0.1` reproduced `PermissionError: [WinError 10013]`; therefore
eight discovered main HTTP tests and one isolation HTTP route test remain unverified
in this restricted execution environment. They were explicitly excluded from the
passing offline runs, without modifying the test sources.

Only the v0.5 RR-specific tests were run for the v0.5 snapshot; its entire historical
suite was not rerun. Browser smoke tests were not run. Existing historical reports
inside the snapshots retain their original dates and are not new verification.

No paid API calls were made. No original desktop/source directory was modified.
Participant-level data, private experiment evidence, databases, PDFs and credentials
are excluded from the public tree. The final publication tree is checked again
before GitHub's main reference is advanced.
