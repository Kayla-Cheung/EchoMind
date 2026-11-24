# EchoMind human-reference analysis

This workspace inspects the Calm Thinking Recognition Ratings data and its
measurement structure. It does not establish individual-agent fidelity.

## Environment

From the EchoMind repository root:

```sh
conda env create -f human-analysis/environment.yml
conda activate echomind-analysis
jupyter lab human-analysis/notebooks/01_data_exploration.ipynb
```

The analysis environment is separate from the standard-library demo/checks. Its
version ranges are not a complete environment lock. Select this environment's
kernel in Jupyter or VS Code; no pre-existing personal Conda installation is
assumed. The notebook finds this checkout when started from the repository,
analysis or notebook directory.

## Permitted input

Obtain the source under its applicable terms; read
[data-access.md](../docs/data-access.md). Keep the original unchanged. Place the
selected reference at `human-analysis/data/raw/rr.csv` (ignored by Git).
The Python 3.11 copy helper accepts an explicit source path on any platform:

```powershell
python human-analysis/copy_data.py "C:\path\to\permitted\rr.csv"
```

It verifies SHA-256, leaves an identical existing copy untouched and refuses to
overwrite a different raw reference. `copy_data.bat` forwards the same source
argument on Windows. No old desktop/archive path is selected automatically.

The notebook fails with an actionable message if the local input is absent. It
does not fall back to another study folder. Input selection and the copy helper
do not certify that a dataset is the correct licensed source; record its origin
and fingerprint as part of the analysis.

## Structure and interpretation

| Location | Purpose |
| --- | --- |
| `data/raw/` | Original permitted reference; never overwrite during analysis |
| `data/processed/` | New derived files; local by default |
| `materials/` | Codebook, variable mapping and dated verification metadata |
| `notebooks/01_data_exploration.ipynb` | Data inspection; publish with outputs cleared |
| `figures/` | Review any derived figure and its permissions before publishing |

The historical reference has 3,259 observation rows and 36 rating columns;
repeated observations are not independent participants. The v0.5 reference uses
1,524 preTest observations. Treat `555` and blanks as missing and preserve the
development/test split. The 1–4 ratings concern semantic similarity, not emotion
intensity or clinical diagnosis. See the codebook for definitions and source
provenance; these counts are not fresh findings from this repository refinement.

Keep original data and saved notebook outputs out of Git. Public software checks
use synthetic inputs and can run without this dataset.
