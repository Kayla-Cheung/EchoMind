# EchoMind v0.5 — Human-Referenced Recognition Ratings

## Purpose

This experiment asks whether model-generated **ordinal similarity ratings** approach the observed distribution of human preTest Recognition Ratings (RR). It is not optimized to produce more negative or neutral labels. The primary descriptive metric is ordinal Wasserstein distance; lower is closer.

## Frozen design

- Seven context conditions are retained: none, plus neutral/negative × direct/transcript/interactive.
- P0 framing is retained. All v0.5 materials, context memories, system prompts, and response specifications are English.
- Temporal distance is fixed to the recent/yesterday variant. There is no T1/T2 ablation.
- Each episode has two separated phases in one conversation:
  1. independently read nine ambiguous scenarios in source order, without rating choices, and answer comprehension questions;
  2. rate four interpretations per scenario on the source 1–4 similarity scale.
- Ratings are integers: 1 Very different, 2 Different, 3 Similar, 4 Very similar. They are not probabilities or emotional-intensity scores.
- The legacy free interpretation/speech/action diagnostic remains conceptually separate and is not converted to or mixed with RR ratings.

## Human reference and split

`rr.csv` contains 3,259 observations, 45 columns, and 36 RR rating columns. The primary reference uses only the 1,524 `preTest` rows. `555` and blanks are treated as missing. Participant IDs are deterministically assigned to an 80% development / 20% held-out split using a private local salt. The salt and participant rows are never committed. Primary reporting compares the three social scenarios' negative and positive target ratings (`ns`, `ps`) with the held-out distribution.

## Source integrity and licensing gate

The local source PDF contains the complete English stimuli, questions, source order, and rating scale. Its SHA-256 is recorded in `data/rr_v05_source_manifest.json`. The public OSF materials node reported no explicit node license, so full item text is stored only in `private_inputs/` (git-ignored) and is not redistributed in the public repository. The participant-level CSV is also local-only.

This implementation reproduces the text content and measurement order, but a text API cannot reproduce the source browser's word-fragment click interaction exactly. That difference must remain in every interpretation of the pilot.

## REAL smoke gate

- No MOCK batch is provided.
- Static compilation, unit/protocol checks, a local prompt preview, source hashes, and a conservative cost preflight must pass first.
- The runner requires `--real`, exactly one episode in each of seven contexts, and a hard budget no greater than USD 0.05.
- The requested and returned model identifiers, full prompts, public model responses, parsed ratings, usage, conservative peak-price cost, latency, failures, and source item hashes are stored in `data/human-rr-v05.sqlite3`.
- Current pricing is checked against DeepSeek's official pricing page before a REAL run. The code uses peak cache-miss input and peak output rates for a conservative bound.

## Interpretation limits

Seven repeated model episodes are not independent human participants. With one episode per condition, each condition has one model rating per item; Wasserstein distances are descriptive pipeline outputs, not a fitted or validated human model. Context conditions should not be pooled as though they were draws from one population. Foils and non-social scenarios are secondary/control outcomes.
