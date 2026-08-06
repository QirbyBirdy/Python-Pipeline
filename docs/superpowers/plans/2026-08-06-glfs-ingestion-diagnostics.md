# GLFS Ingestion & Diagnostics Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the GLFS pipeline skeleton — ingest the `ind` and `emig` datasets into a stable working format, produce exploratory diagnostics, and draft a problem inventory, with no cleaning/transformation code.

**Architecture:** A `Scripts/` folder holding `config.py` (all paths), a `glfs_pipeline/` package with one module per stage (`ingest.py`, `diagnostics.py`, `problem_inventory.py`), and a `run_pipeline.py` CLI entrypoint that chains the three stages per dataset. Each stage is a pure function taking `(name, datasets_dict)` and returns the path(s) it wrote — no module imports `config` directly except `run_pipeline.py`, which passes `config.DATASETS` in. This keeps every stage runnable and testable in isolation, and matches the design in `docs/superpowers/specs/2026-08-06-glfs-ingestion-diagnostics-design.md`.

**Tech Stack:** Python, pandas, pyarrow (parquet I/O).

## Global Constraints

- No cleaning/transformation code in this phase — ingest, diagnostics, and problem_inventory are read-only with respect to values.
- No unit test framework — this is a one-shot exploratory pipeline; verification is running each stage and inspecting its output (per approved spec).
- `ind` and `emig` are treated as two independent tracks; they are not merged.
- The dictionary's `choices` column is a Stata value-label-*set name* only (e.g. `yesno`), not an enumerated code list — diagnostics reports it as-is with no in/out-of-range judgment.
- All pipeline code lives under `Scripts/`; all generated output lives under `Outputs/`; raw data stays under `Data/` untouched.
- CSV columns are read as `dtype=str` (GLFS data is coded/categorical; no silent numeric coercion).

---

### Task 1: Dependencies and package skeleton

**Files:**
- Create: `requirements.txt`
- Create: `Scripts/glfs_pipeline/__init__.py`
- Create: `.gitignore` (append if it doesn't exist)

**Interfaces:**
- Produces: `Scripts/glfs_pipeline/` importable as a package from `Scripts/run_pipeline.py`.

- [ ] **Step 1: Create `requirements.txt`**

```text
pandas>=2.0
pyarrow>=14.0
```

- [ ] **Step 2: Create the empty package marker**

`Scripts/glfs_pipeline/__init__.py`:

```python
"""GLFS pipeline stages: ingest, diagnostics, problem_inventory."""
```

- [ ] **Step 3: Add `.gitignore` entry for the interim cache**

Create (or append to) `.gitignore` at the project root with:

```text
Outputs/interim/
```

Reasoning: `Outputs/interim/*.parquet` is a regenerable working-copy cache of the raw CSVs, not a deliverable — the diagnostics CSVs, reports, and problem-inventory drafts under `Outputs/diagnostics/` and `Outputs/problem_inventory/` are the actual deliverables and stay tracked.

- [ ] **Step 4: Install dependencies**

Run: `python -m pip install -r requirements.txt`
Expected: pandas and pyarrow install without error.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt Scripts/glfs_pipeline/__init__.py .gitignore
git commit -m "Add pipeline dependencies and package skeleton"
```

---

### Task 2: Ingest stage

**Files:**
- Create: `Scripts/glfs_pipeline/ingest.py`

**Interfaces:**
- Consumes: `config.DATASETS` dict, shape `{"ind": {"csv": Path, "dictionary": Path, "interim": Path, ...}, "emig": {...}}` (already defined in `Scripts/config.py`).
- Produces:
  - `load_dataset(name: str, datasets: dict) -> pandas.DataFrame`
  - `ingest(name: str, datasets: dict) -> pathlib.Path` (path to the written parquet)
  - `ingest_all(datasets: dict) -> dict[str, pathlib.Path]`

- [ ] **Step 1: Write `Scripts/glfs_pipeline/ingest.py`**

```python
"""Stage 1: read raw GLFS CSVs, validate against their dictionaries, and
write a dtype-stable working copy to Outputs/interim/*.parquet."""

from pathlib import Path

import pandas as pd


def load_dataset(name: str, datasets: dict) -> pd.DataFrame:
    paths = datasets[name]
    df = pd.read_csv(paths["csv"], dtype=str)
    dictionary = pd.read_csv(paths["dictionary"])

    dict_columns = set(dictionary["column"])
    csv_columns = set(df.columns)
    missing_in_csv = dict_columns - csv_columns
    missing_in_dict = csv_columns - dict_columns
    if missing_in_csv or missing_in_dict:
        raise ValueError(
            f"Column mismatch for '{name}': "
            f"in dictionary but not CSV: {sorted(missing_in_csv)}; "
            f"in CSV but not dictionary: {sorted(missing_in_dict)}"
        )
    return df


def ingest(name: str, datasets: dict) -> Path:
    df = load_dataset(name, datasets)
    out_path = datasets[name]["interim"]
    df.to_parquet(out_path, index=False)
    return out_path


def ingest_all(datasets: dict) -> dict:
    return {name: ingest(name, datasets) for name in datasets}
```

- [ ] **Step 2: Run it and verify**

Run:

```bash
python -c "import sys; sys.path.insert(0, 'Scripts'); import config; from glfs_pipeline.ingest import ingest_all; result = ingest_all(config.DATASETS); print(result)"
```

Expected: prints a dict with `ind` and `emig` mapped to their `.parquet` paths, no exception. Then confirm the files exist and are non-trivial size:

```bash
ls -la Outputs/interim/
```

Expected: `ind_raw.parquet` and `emig_raw.parquet` present, both > 0 bytes.

- [ ] **Step 3: Commit**

```bash
git add Scripts/glfs_pipeline/ingest.py
git commit -m "Add ingest stage: raw CSV -> validated interim parquet"
```

---

### Task 3: Diagnostics stage

**Files:**
- Create: `Scripts/glfs_pipeline/diagnostics.py`

**Interfaces:**
- Consumes: `datasets[name]["interim"]` (parquet written by Task 2), `datasets[name]["dictionary"]`, `datasets[name]["diagnostics_csv"]`, `datasets[name]["diagnostics_report"]`.
- Produces:
  - `column_diagnostics(df: pandas.DataFrame, dictionary: pandas.DataFrame) -> pandas.DataFrame` with columns `column, dtype, pct_missing, n_unique, top_values, label_set`
  - `render_report(name: str, df: pandas.DataFrame, diagnostics: pandas.DataFrame) -> str`
  - `diagnose(name: str, datasets: dict) -> tuple[pathlib.Path, pathlib.Path]`
  - `diagnose_all(datasets: dict) -> dict[str, tuple[pathlib.Path, pathlib.Path]]`

- [ ] **Step 1: Write `Scripts/glfs_pipeline/diagnostics.py`**

```python
"""Stage 2: per-column exploratory diagnostics on the interim parquet."""

from pathlib import Path

import pandas as pd


def column_diagnostics(df: pd.DataFrame, dictionary: pd.DataFrame) -> pd.DataFrame:
    label_set_by_column = dict(zip(dictionary["column"], dictionary["choices"]))
    n_rows = len(df)
    rows = []
    for col in df.columns:
        series = df[col]
        n_missing = int(series.isna().sum())
        top_counts = series.value_counts(dropna=True).head(5)
        rows.append(
            {
                "column": col,
                "dtype": str(series.dtype),
                "pct_missing": round(100 * n_missing / n_rows, 2) if n_rows else 0.0,
                "n_unique": int(series.nunique(dropna=True)),
                "top_values": "; ".join(f"{val}={cnt}" for val, cnt in top_counts.items()),
                "label_set": label_set_by_column.get(col, "") or "",
            }
        )
    return pd.DataFrame(rows)


def render_report(name: str, df: pd.DataFrame, diagnostics: pd.DataFrame) -> str:
    n_rows, n_cols = df.shape
    overall_missing = diagnostics["pct_missing"].mean() if n_cols else 0.0
    flagged = diagnostics.loc[diagnostics["pct_missing"] > 50, "column"].tolist()
    constant_cols = diagnostics.loc[diagnostics["n_unique"] <= 1, "column"].tolist()

    lines = [
        f"# Diagnostics report: {name}",
        "",
        f"- Rows: {n_rows}",
        f"- Columns: {n_cols}",
        f"- Average missingness across columns: {overall_missing:.2f}%",
        "",
        f"## Columns >50% missing ({len(flagged)})",
        "",
    ]
    lines += [f"- {c}" for c in flagged] if flagged else ["- none"]
    lines += ["", f"## Constant / single-value columns ({len(constant_cols)})", ""]
    lines += [f"- {c}" for c in constant_cols] if constant_cols else ["- none"]
    return "\n".join(lines) + "\n"


def diagnose(name: str, datasets: dict) -> tuple[Path, Path]:
    paths = datasets[name]
    df = pd.read_parquet(paths["interim"])
    dictionary = pd.read_csv(paths["dictionary"])

    diagnostics = column_diagnostics(df, dictionary)
    diagnostics.to_csv(paths["diagnostics_csv"], index=False)

    report = render_report(name, df, diagnostics)
    paths["diagnostics_report"].write_text(report, encoding="utf-8")

    return paths["diagnostics_csv"], paths["diagnostics_report"]


def diagnose_all(datasets: dict) -> dict:
    return {name: diagnose(name, datasets) for name in datasets}
```

- [ ] **Step 2: Run it and verify**

Run:

```bash
python -c "import sys; sys.path.insert(0, 'Scripts'); import config; from glfs_pipeline.diagnostics import diagnose_all; result = diagnose_all(config.DATASETS); print(result)"
```

Expected: prints a dict with `ind` and `emig` mapped to `(csv_path, report_path)` tuples, no exception.

Then inspect the outputs (use `cat`/Bash, not the Read tool — `Outputs/**` reads are denied by the project's `settings.json`):

```bash
cat Outputs/diagnostics/ind_report.md
wc -l Outputs/diagnostics/ind_diagnostics.csv Outputs/diagnostics/emig_diagnostics.csv
```

Expected: `ind_report.md` shows plausible row/column counts (13853 data rows, ~176 columns) and a missingness summary; both diagnostics CSVs have one row per dataset column plus a header.

- [ ] **Step 3: Commit**

```bash
git add Scripts/glfs_pipeline/diagnostics.py
git commit -m "Add diagnostics stage: per-column missingness, uniqueness, label-set report"
```

---

### Task 4: Problem inventory stage

**Files:**
- Create: `Scripts/glfs_pipeline/problem_inventory.py`

**Interfaces:**
- Consumes: `datasets[name]["diagnostics_csv"]` (written by Task 3, columns: `column, dtype, pct_missing, n_unique, top_values, label_set`), `datasets[name]["problem_inventory"]`.
- Produces:
  - `draft_findings(diagnostics: pandas.DataFrame) -> pandas.DataFrame` with columns `column, issue, severity, label_set, n_unique, pct_missing`
  - `render_inventory(name: str, findings: pandas.DataFrame) -> str`
  - `draft(name: str, datasets: dict) -> pathlib.Path`
  - `draft_all(datasets: dict) -> dict[str, pathlib.Path]`

- [ ] **Step 1: Write `Scripts/glfs_pipeline/problem_inventory.py`**

```python
"""Stage 3: draft a severity-ranked, human-editable problem inventory from
the diagnostics table. Descriptive only -- no data is altered here."""

from pathlib import Path

import pandas as pd


def _severity(row: pd.Series) -> str:
    if row["pct_missing"] > 50:
        return "High"
    if row["n_unique"] <= 1:
        return "Medium"
    return "Informational"


def _issue(row: pd.Series) -> str:
    if row["pct_missing"] > 50:
        return f"{row['pct_missing']}% missing"
    if row["n_unique"] <= 1:
        return "constant / single-value column"
    return "no issue detected"


def draft_findings(diagnostics: pd.DataFrame) -> pd.DataFrame:
    findings = diagnostics.copy()
    findings["severity"] = findings.apply(_severity, axis=1)
    findings["issue"] = findings.apply(_issue, axis=1)

    order = {"High": 0, "Medium": 1, "Informational": 2}
    findings["_order"] = findings["severity"].map(order)
    findings = findings.sort_values(["_order", "column"]).drop(columns="_order")

    return findings[["column", "issue", "severity", "label_set", "n_unique", "pct_missing"]]


def render_inventory(name: str, findings: pd.DataFrame) -> str:
    lines = [
        f"# Problem inventory (draft): {name}",
        "",
        "Auto-drafted from diagnostics. Descriptive only -- no cleaning applied. Edit freely.",
        "",
        "| Column | Issue | Severity | Label set | # unique | % missing |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for _, row in findings.iterrows():
        lines.append(
            f"| {row['column']} | {row['issue']} | {row['severity']} | "
            f"{row['label_set']} | {row['n_unique']} | {row['pct_missing']} |"
        )
    return "\n".join(lines) + "\n"


def draft(name: str, datasets: dict) -> Path:
    paths = datasets[name]
    diagnostics = pd.read_csv(paths["diagnostics_csv"])
    findings = draft_findings(diagnostics)
    inventory = render_inventory(name, findings)
    paths["problem_inventory"].write_text(inventory, encoding="utf-8")
    return paths["problem_inventory"]


def draft_all(datasets: dict) -> dict:
    return {name: draft(name, datasets) for name in datasets}
```

- [ ] **Step 2: Run it and verify**

Run:

```bash
python -c "import sys; sys.path.insert(0, 'Scripts'); import config; from glfs_pipeline.problem_inventory import draft_all; result = draft_all(config.DATASETS); print(result)"
```

Expected: prints a dict with `ind` and `emig` mapped to their `_problem_inventory.md` paths, no exception.

```bash
cat Outputs/problem_inventory/ind_problem_inventory.md
```

Expected: a markdown table sorted High → Medium → Informational severity, one row per column of the `ind` dataset.

- [ ] **Step 3: Commit**

```bash
git add Scripts/glfs_pipeline/problem_inventory.py
git commit -m "Add problem_inventory stage: auto-drafted severity-ranked findings"
```

---

### Task 5: CLI entrypoint and end-to-end run

**Files:**
- Create: `Scripts/run_pipeline.py`

**Interfaces:**
- Consumes: `config.DATASETS`; `ingest`, `diagnose`, `draft` from Tasks 2-4.
- Produces: a runnable CLI (`python Scripts/run_pipeline.py [--dataset ind|emig|both]`).

- [ ] **Step 1: Write `Scripts/run_pipeline.py`**

```python
"""CLI entrypoint: run ingest -> diagnostics -> problem_inventory for one or
both GLFS datasets.

Usage:
    python Scripts/run_pipeline.py [--dataset ind|emig|both]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from glfs_pipeline.diagnostics import diagnose
from glfs_pipeline.ingest import ingest
from glfs_pipeline.problem_inventory import draft


def run(dataset: str) -> None:
    names = list(config.DATASETS) if dataset == "both" else [dataset]
    for name in names:
        print(f"[{name}] ingesting...")
        ingest(name, config.DATASETS)
        print(f"[{name}] running diagnostics...")
        diagnose(name, config.DATASETS)
        print(f"[{name}] drafting problem inventory...")
        draft(name, config.DATASETS)
        print(f"[{name}] done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the GLFS ingestion/diagnostics pipeline."
    )
    parser.add_argument("--dataset", choices=["ind", "emig", "both"], default="both")
    args = parser.parse_args()
    run(args.dataset)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full pipeline end to end**

Run: `python Scripts/run_pipeline.py`
Expected: six `[name] ...` progress lines per dataset (ingesting/diagnostics/inventory/done for `ind` and for `emig`), no traceback.

- [ ] **Step 3: Verify all expected outputs exist**

```bash
ls Outputs/interim/ Outputs/diagnostics/ Outputs/problem_inventory/
```

Expected: `ind_raw.parquet`, `emig_raw.parquet` in `interim/`; `ind_diagnostics.csv`, `ind_report.md`, `emig_diagnostics.csv`, `emig_report.md` in `diagnostics/`; `ind_problem_inventory.md`, `emig_problem_inventory.md` in `problem_inventory/`.

- [ ] **Step 4: Commit**

```bash
git add Scripts/run_pipeline.py Outputs/diagnostics Outputs/problem_inventory
git commit -m "Add run_pipeline CLI entrypoint and generated diagnostics/problem-inventory output"
```
