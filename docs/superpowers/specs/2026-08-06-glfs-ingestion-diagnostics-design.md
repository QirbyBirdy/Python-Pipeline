# GLFS Ingestion & Diagnostics Pipeline — Design

Date: 2026-08-06

## Purpose

Stand up the project skeleton for the GLFS (Guyana Labour Force Survey, round 174)
data pipeline: get the raw individual (`ind`) and emigration-module (`emig`) datasets
ingested into a stable working format, produce exploratory diagnostics on each, and
draft a problem inventory of data-quality issues. This phase is deliberately scoped
to stop before any cleaning/transformation code — cleaning will be a separate,
later phase built on top of the problem inventory.

## Scope

Two parallel tracks, `ind` and `emig`, each independently pushed through three
stages: ingest → diagnostics → problem inventory. The two datasets are related via
`hhid` but are not merged in this phase — they have different units of analysis
(individual vs. emigrant record) and merging is out of scope until cleaning begins.

## File layout

```text
requirements.txt                   # pandas, pyarrow
Scripts/
  config.py                        # path constants (pathlib), Outputs/ subdirs auto-created
  glfs_pipeline/
    __init__.py
    ingest.py                      # raw CSV -> validated -> interim parquet
    diagnostics.py                 # interim parquet -> per-column diagnostics
    problem_inventory.py           # diagnostics -> drafted markdown inventory
  run_pipeline.py                  # CLI entrypoint, runs both datasets through all 3 stages
Outputs/
  interim/      ind_raw.parquet, emig_raw.parquet
  diagnostics/  ind_diagnostics.csv, ind_report.md, emig_diagnostics.csv, emig_report.md
  problem_inventory/  ind_problem_inventory.md, emig_problem_inventory.md
```

`Scripts/` (pre-existing, currently empty) is kept and used as the container
for `config.py`, the `glfs_pipeline/` package, and `run_pipeline.py` — all
pipeline code lives under `Scripts/`, all pipeline output under `Outputs/`,
and raw data under `Data/`.

## Components

### `config.py`

Central source of truth for every path used by the pipeline: raw data files under
`Data/`, the interim/diagnostics/problem-inventory output directories under
`Outputs/`. Uses `pathlib.Path`, resolved relative to the project root (the file's
own location), so scripts work regardless of the current working directory.
Creates the `Outputs/` subdirectories on import if they don't already exist.

### `glfs_pipeline/ingest.py`

For each dataset (`ind`, `emig`):
- Reads the raw CSV with every column as string dtype (`dtype=str`) — GLFS data is
  almost entirely coded/categorical, so no silent numeric coercion happens at this
  stage.
- Reads the matching `*-dictionary.csv` and checks its `column` list matches the
  CSV's columns exactly (order-insensitive); any mismatch is reported and raises.
- Writes the raw frame unchanged to `Outputs/interim/<name>_raw.parquet`.

No value transformation happens here — this stage only gets the data into a fast,
dtype-stable working copy that later stages read instead of re-parsing the CSV.

### `glfs_pipeline/diagnostics.py`

For each dataset, computes a per-column diagnostics table:
- dtype, % missing, # unique values, top 5 value counts
- the dictionary's `choices` value for that column, reported as-is

Note: the dictionary's `choices` column is a Stata value-label-*set name*
(e.g. `yesno`, `Sex`, `Educ`), not an enumerated list of valid codes — and the
`ind` dataset has no accompanying `.dta` file to resolve real label mappings
from. There is nothing to validate observed values against, so this stage
reports the label-set name for context only and makes no in/out-of-range
judgment.

Writes the table to `Outputs/diagnostics/<name>_diagnostics.csv` and renders a
human-readable summary to `Outputs/diagnostics/<name>_report.md` (dataset shape,
overall missingness, list of flagged columns).

### `glfs_pipeline/problem_inventory.py`

Reads the diagnostics CSV and applies fixed heuristics to draft a severity-ranked
markdown inventory — a starting point for manual review, not a final judgment:

| Condition | Severity |
| --- | --- |
| >50% missing | High |
| constant / single-value column | Medium |
| everything else | Informational |

Writes `Outputs/problem_inventory/<name>_problem_inventory.md`. This stage is
purely descriptive — no data is altered, and no cleaning decisions are made.

### `run_pipeline.py`

CLI entrypoint: `python run_pipeline.py [--dataset ind|emig|both]` (default `both`).
Runs ingest → diagnostics → problem_inventory in order for the selected dataset(s).

## Data flow

```
Data/glfs-174-<name>-public.csv  ─┐
Data/glfs-174-<name>-public-dictionary.csv ─┘─▶ ingest.py ─▶ Outputs/interim/<name>_raw.parquet
                                                                     │
                                                                     ▼
                                                          diagnostics.py
                                                                     │
                                        ┌────────────────────────────┴───────────────────────────┐
                                        ▼                                                          ▼
                     Outputs/diagnostics/<name>_diagnostics.csv                Outputs/diagnostics/<name>_report.md
                                        │
                                        ▼
                              problem_inventory.py
                                        │
                                        ▼
                    Outputs/problem_inventory/<name>_problem_inventory.md
```

## Error handling

Ingestion fails loudly (raises) if a raw CSV is missing or its columns don't match
the dictionary — that indicates a real structural problem with the input, not
something to paper over silently. Each stage is idempotent: rerunning a stage
simply overwrites its own output files.

## Testing

No unit test suite. This is a one-shot exploratory data pipeline, not a shipped
software product — correctness is verified by running it end-to-end and reading
the generated diagnostics/report/inventory files. Adding a test framework here
would be scope creep relative to the actual goal (get a first look at the data).

## Explicitly out of scope (this phase)

- Any data cleaning, recoding, or transformation
- Merging `ind` and `emig`
- Using the `.dta` file (the `emig` CSV already carries the same data; `.dta` is
  redundant for this phase)
- Parsing the methodological-report PDF
