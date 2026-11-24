# EchoMind repository review and refinement

Date: 2026-11-23. Target: consolidated checkout at base commit
`51947e148fd3df3f126b9c5924cb04a172236bbe`. The surrounding legacy working tree
has unrelated existing changes and is outside this refinement.

## Comparators inspected

These are established, directly relevant study repositories, not assumed to be
perfect software-engineering templates. The comparison inspected their top-level
file inventories and README instructions through GitHub. It did not run their
experiments or audit their complete implementations.

| Repository and inspected revision | Useful practice observed | EchoMind application |
| --- | --- | --- |
| [WekenborgLab/LLMAffect](https://github.com/WekenborgLab/LLMAffect/tree/07466ff29e1314e2916d758a95360d4eaee72d07) | Tested Python version, requirements, named experimental phases, example CLI and links from acquisition to plotting/analysis scripts | Specify the runtime, map the protocols, and distinguish running checks from collecting new model data |
| [marcelbinz/Llama-3.1-Centaur-70B](https://github.com/marcelbinz/Llama-3.1-Centaur-70B/tree/f8038fb57e052614a1d0aae3e58bf5cca93da883) | Paper/model linkage, inference examples, explicit resource requirements, tested dependency versions, and separate analysis/generalization directories | Make the scientific question and evidence boundary visible; document separate environments and reproduction requirements |
| [StanfordHCI/genagents](https://github.com/StanfordHCI/genagents/tree/96854071ef4c2d79c93144c973c7820722d52bab) | Repository map, installation/usage examples and an explicit distinction between available examples and restricted participant-agent access | Explain what a public clone contains and what requires permitted private material; never imply all human data are bundled |

EchoMind does not copy these projects' licensing choices, model assumptions,
credential-storage examples or research claims. CI and integrity checks below
are EchoMind-specific engineering improvements, not practices attributed to all
three comparators.

## Findings and changes

| Area | Before this review | Refinement |
| --- | --- | --- |
| Research entry point | Long historical workbench README; current consolidated snapshots difficult to discover | Short English README with research status, experiment table, commands and evidence limits; old guide retained as `WORKBENCH_GUIDE.md` |
| Version selection | Multiple copies of modules such as `rr_v05.py`; ad hoc per-version commands | Machine-readable experiment index; verification uses separate interpreters for every version |
| Historical integrity | Consolidation hashes existed, with machine-dependent raw line endings | Additional LF-normalized integrity manifest for all 309 historical public files; original raw-byte manifest preserved |
| Fresh-clone verification | Root unit tests and private-fixture-dependent RR tests had no common entry point | Standard-library check runner and synthetic public RR protocol checks; no original task text, human data or model calls needed |
| Test scope | Localhost restrictions previously caused failures and manual exclusions | Default exclusions printed by exact test ID; explicit HTTP scope preflights loopback and fails if unavailable |
| Continuous checks | No workflow found | Linux/Windows Python 3.11 workflow with all core localhost tests plus isolated snapshot checks; no model credentials supplied |
| Public artifacts | Git ignore rules and a one-time audit | Repeatable check of tracked plus non-ignored untracked files, private paths, obvious credential patterns and notebook output |
| Contribution workflow | No root contributor/agent guide found | Scope, review/check commands, data rules and research invariants in `CONTRIBUTING.md` and `AGENTS.md` |
| Analysis portability | Notebook silently fell back to a personal archive path; copy helper could overwrite a raw CSV | Checkout-relative explicit input, missing-data error, source/copy hashes and refusal to overwrite different raw data; statistical calculations unchanged |
| Reproduction expectations | Private evidence present locally; source snapshots had old absolute-path helpers | Public software checks versus historical-result reproduction explicitly documented; old helpers not advertised as portable entry points |

No scientific prompts, model settings, historical experiment code, raw records or
historical results were changed. The analysis notebook's input-selection cell was
made portable; its statistical cells remain unchanged. All 310 files listed in the original consolidation
manifest were checked against its raw-byte hashes. That list includes six ignored
local smoke exports and omits five public data/configuration manifests. The new
integrity manifest covers the 309 actually public snapshot files; ignored exports
remain local and are not required by public verification.

## Verification scope

The supported command is `python scripts/run_checks.py --snapshots`; add `--http`
for localhost integration. The runner prints actual executed counts and the
excluded tests.

Verification completed on 2026-11-23 using temporary public-only exports, with
only tracked/non-ignored public files staged in temporary Git repositories.
No private input directories, historical model outputs, participant CSV or
tokenizer ZIP was copied into those verification trees.

| Scope | Observed result |
| --- | --- |
| Latest public-only core suite | 86 tests passed, including the analysis path/import and repository guard regressions |
| Public-only v0.3 acquisition suite | 23 tests passed |
| Public-only v0.4 acquisition suite | 23 tests passed |
| Public-only v0.5 synthetic RR smoke | 4 tests passed |
| Public-only RR-isolation synthetic smoke | 4 tests passed |
| Total distinct tests across these scopes | 140 passed |
| Public file audit | 428 public files checked; 309 snapshot fingerprints matched |
| Original consolidation evidence | All 310 original raw-byte fingerprints still matched |
| Analysis notebook diff | Only input-selection cell 4 changed; other cells equal to base commit; outputs remain cleared |
| Maintained local documentation links and Python syntax | Passed |
| Workflow YAML syntax and Linux/Windows matrix | Parsed and checked locally |
| `git diff --check` | Passed |
| Explicit HTTP scope | Preflight failed with Windows socket error 10013; 8 core localhost tests remain unverified here |

Counts combine the final public-only core run with the four passing public-only
snapshot scopes. The snapshot sources and fingerprints were unchanged between
these runs. The data importer uses standard-library Python on both platforms.

CI configuration is local and has not run on GitHub. No real model calls, human
experiments, historical data regeneration, commit, push or publication occurred.

## Remaining scientific and release work

- A permitted private-input reproduction procedure is still needed to independently
  recreate historical numerical results. Old private fixture tests include
  machine-specific paths and cannot be claimed as public-clone coverage.
- Population marginal distances are not matched-person validation. The unprimed
  human reference, tiny model repetitions, inspected test set and packetization
  confounds still bound the RR pilot's interpretation.
- Freeze a new protocol and genuinely fresh evaluation data before using future
  results to support person-specific prediction or selecting a better method.
- Root runtime checks use the standard library. The separate analysis environment
  uses version ranges; an analysis release needs a tested environment lock and
  analysis-to-figure reproduction commands.
- Authorship, a project license and a citable release/archive identifier remain
  unresolved. None was invented during maintenance. Third-party material rights
  must remain separate from any future code license.
- The snapshots intentionally retain duplicate historical code. Refactoring them
  into a shared library would require demonstrating protocol equivalence and
  merits a separate change rather than rewriting this provenance record.
