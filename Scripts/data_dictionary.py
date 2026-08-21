"""Stage 5 (build brief Step 8 / Section 4.2): the data dictionary
deliverable -- one row per variable, covering every column in the final
(imputed) dataset, not just the five named cleaning/imputation-scope
variables. A reviewer opening the exported data needs to understand every
column, not only the ones this project's cleaning stage touched.

Required columns per the brief: name, type, label, valid range or value
set, % missing in raw data, % missing after cleaning, imputation
treatment, notes. "Raw" here means Outputs/typed/<name>_typed.parquet --
right after ingest.py's dtype conversion, before clean.py has touched a
single sentinel value -- since the true raw CSV (all-string dtype) would
give a less meaningful type/range readout. Derived columns (the four
ISIC/ISCO classification columns clean.py adds, the <column>_imputed flag
columns impute.py adds) did not exist at that point, so their "raw"
missingness is reported as not applicable rather than a fabricated number.

Writes Outputs/data_dictionary/<name>_data_dictionary.csv and the same
table as a single-sheet .xlsx (brief: "included as a sheet in the Excel
output and also saved as CSV" -- the export stage, brief Step 9, is what
merges this sheet into the final combined workbook alongside the data;
this module is the one source of truth it will read from).
"""

from pathlib import Path

import pandas as pd

import config

# Labels for columns that don't exist in the source CSV dictionaries
# because clean.py / impute.py added them.
_DERIVED_LABELS = {
    "isic_section": "Derived: ISIC Rev.4 section letter (A-U), from isic_code (clean.py)",
    "isic_section_label": "Derived: full ISIC Rev.4 section title, from isic_section (clean.py)",
    "isco_major_group": "Derived: ISCO-08 major group digit (0-9), from isco_code (clean.py)",
    "isco_major_group_label": "Derived: full ISCO-08 major group title, from isco_major_group (clean.py)",
}

# Columns clean.py / impute.py actually did something to, with the real
# evidence-backed story -- kept here rather than fabricated for every
# column so the honestly-untouched majority of columns say so plainly.
_NOTES = {
    "ind": {
        "hhid": "Household ID; part of the hhid+member dedup key in clean.py (0 duplicates found).",
        "member": "Person-within-household ID; part of the hhid+member dedup key in clean.py (0 duplicates found).",
        "q1_03": "0% missing; no cleaning issues found (problem_inventory.py).",
        "q1_04": "Sentinel -1 ('don't know') corrected to NaN in clean.py (12 rows), then median-imputed in impute.py.",
        "q3_03": "Sentinel 99 (top-code) corrected to NaN in clean.py (88 rows), then median-imputed in impute.py "
                 "(population: has a main job, q3_16 not null).",
        "q3_04": "Missingness is 100% structural (gated by q3_01 == 'Yes'); left missing, not imputed "
                 "(0 incidental gaps confirmed among the 163 rows the question applies to).",
        "q3_05": "Derived: recomputed from q3_03 + q3_04 (clean.py, then again in impute.py after q3_03 was "
                 "imputed), not independently corrected or imputed. Structurally gated by q3_01 == 'Yes', same as q3_04.",
        "q3_08": "Sentinel -1 corrected to NaN in clean.py (1 row), then median-imputed in impute.py, restricted "
                 "to respondents with a second job (q3_01 == 'Yes') -- imputing over the 'has a main job' "
                 "population instead would have manufactured 4,626 fake values.",
        "q3_09": "Derived: recomputed from the seven daily-hours columns q3_07_1..7 (clean.py, then again in "
                 "impute.py), not independently corrected or imputed.",
        "q3_10": "Derived: recomputed from q3_09 + q3_08 (clean.py, then again in impute.py), not independently "
                 "corrected or imputed.",
        "isic_code": "Leading zero stripped on export for some codes (e.g. '0729' -> '729'); corrected via "
                     "zero-padding in classify_isic_section(). Missingness (9,064 rows) is 100% structural "
                     "(no main job); left missing, not imputed.",
        "isco_code": "Same leading-zero export issue as isic_code, corrected the same way. Missingness is 100% "
                     "structural (no main job); left missing, not imputed.",
        "panelid": "Named like a unique respondent ID but is not one -- only 18 distinct values across 13,853 "
                   "rows (a panel/wave grouping code). Not used as a join key anywhere in this pipeline "
                   "(problem_inventory.py).",
    },
    "emig": {
        "hhid": "Household ID; part of the hhid+emig dedup key in clean.py (0 duplicates found).",
        "emig": "Emigrant-within-household ID; part of the hhid+emig dedup key in clean.py (0 duplicates found).",
        "q7_06": "Sentinel -1 ('don't know') corrected to NaN in clean.py (28 rows), then median-imputed in impute.py.",
    },
}
for i in range(1, 8):
    _NOTES["ind"][f"q3_07_{i}"] = (
        "Sentinel -1 corrected to NaN in clean.py, then median-imputed in impute.py "
        "(population: has a main job, q3_16 not null)."
    )


def _pct_missing(series: pd.Series, n: int):
    return round(100 * float(series.isna().sum()) / n, 2) if n else 0.0


def _value_set_or_range(series: pd.Series, max_values: int = 8) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return ""
    dtype_str = str(series.dtype)
    if dtype_str in ("category", "boolean"):
        uniques = sorted(str(v) for v in non_null.unique())
        if len(uniques) <= max_values:
            return "; ".join(uniques)
        return f"{len(uniques)} distinct values"
    if pd.api.types.is_numeric_dtype(series):
        return f"{non_null.min()}–{non_null.max()}"
    if dtype_str == "string":
        uniques = non_null.unique()
        if len(uniques) <= max_values:
            return "; ".join(sorted(str(v) for v in uniques))
        return f"free text ({len(uniques)} distinct values)"
    return f"{non_null.nunique()} distinct values"


def _imputation_treatment(name: str, col: str, imputed_df: pd.DataFrame, pct_cleaned) -> str:
    flag_col = f"{col}_imputed"
    if flag_col in imputed_df.columns:
        n_imputed = int(imputed_df[flag_col].sum())
        return f"Median imputation, {n_imputed} row(s) filled (see {name}_imputed.parquet)"
    if col.endswith("_imputed"):
        return "N/A -- this column is itself an imputation flag"
    if col in ("isic_code", "isco_code") or (name == "ind" and col == "q3_04"):
        return "Left missing (confirmed structural -- see notes)"
    if not pct_cleaned:
        return "N/A (no missing values)"
    return "Not imputed -- outside assigned cleaning/imputation scope"


def _programmatic_notes(name: str, col: str) -> str:
    notes = []
    if col in config.FREE_TEXT_COLUMNS.get(name, []):
        notes.append(
            "Free-text response; near-duplicate values (>=0.98 similarity) auto-consolidated to their "
            "most frequent form in clean.py."
        )
    if col in config.MONETARY_COLUMNS.get(name, []):
        notes.append(
            "Checked for outliers via 1.5x IQR in clean.py (flag-only, see <name>_flagged_for_review.csv)."
        )
    for dependent_col, gate_col, applies_when in config.SKIP_PATTERNS.get(name, []):
        if dependent_col == col:
            notes.append(f"Structurally gated by {gate_col} == '{applies_when}' (see config.SKIP_PATTERNS).")
    return " ".join(notes)


def column_labels(name: str, datasets: dict, columns) -> dict:
    """Variable label per column name -- from the source CSV dictionary's
    `description` for original survey columns, `_DERIVED_LABELS` for the
    columns clean.py added, and a generated label for each impute.py
    `<column>_imputed` flag. Shared with export.py so the labels attached
    to the .sav/.dta files are the exact same ones documented in the data
    dictionary, not a second copy that could drift from it."""
    paths = datasets[name]
    source_dict = pd.read_csv(paths["dictionary"])
    base_labels = dict(zip(source_dict["column"], source_dict["description"]))

    labels = {}
    for col in columns:
        label = base_labels.get(col) or _DERIVED_LABELS.get(col)
        if label is None and col.endswith("_imputed"):
            base = col[: -len("_imputed")]
            label = f"Flag: True if '{base_labels.get(base, base)}' ({base}) was filled by median imputation (impute.py)"
        labels[col] = label or ""
    return labels


def build_dictionary(name: str, datasets: dict) -> pd.DataFrame:
    """One row per column of Outputs/typed/<name>_imputed.parquet. Requires
    ingest.py, clean.py, and impute.py to have already run."""
    paths = datasets[name]
    typed = pd.read_parquet(paths["typed"])
    cleaned = pd.read_parquet(paths["cleaned"])
    imputed = pd.read_parquet(paths["imputed"])

    labels = column_labels(name, datasets, imputed.columns)

    rows = []
    for col in imputed.columns:
        label = labels[col]

        pct_raw = _pct_missing(typed[col], len(typed)) if col in typed.columns else None
        pct_cleaned = _pct_missing(cleaned[col], len(cleaned)) if col in cleaned.columns else None

        note = _NOTES.get(name, {}).get(col, "") or _programmatic_notes(name, col)

        rows.append(
            {
                "variable": col,
                "type": str(imputed[col].dtype),
                "label": label,
                "value_set_or_range": _value_set_or_range(imputed[col]),
                "pct_missing_raw": pct_raw if pct_raw is not None else "N/A (derived column)",
                "pct_missing_cleaned": pct_cleaned if pct_cleaned is not None else "N/A (derived column)",
                "imputation_treatment": _imputation_treatment(name, col, imputed, pct_cleaned),
                "notes": note,
            }
        )
    return pd.DataFrame(rows)


def write_dictionary(name: str, datasets: dict) -> Path:
    paths = datasets[name]
    dictionary = build_dictionary(name, datasets)

    dictionary.to_csv(paths["data_dictionary_csv"], index=False)
    with pd.ExcelWriter(paths["data_dictionary_xlsx"], engine="openpyxl") as writer:
        dictionary.to_excel(writer, sheet_name="data_dictionary", index=False)

    n_vars = len(dictionary)
    n_imputed_vars = int((dictionary["imputation_treatment"].str.startswith("Median imputation")).sum())
    n_left_structural = int((dictionary["imputation_treatment"] == "Left missing (confirmed structural -- see notes)").sum())
    log_lines = [
        f"Data dictionary: {name}",
        f"Variables documented: {n_vars}",
        f"Variables imputed: {n_imputed_vars}",
        f"Variables left missing (confirmed structural): {n_left_structural}",
        f"Written to {paths['data_dictionary_csv'].name} and {paths['data_dictionary_xlsx'].name}",
    ]
    paths["data_dictionary_log"].write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print("\n".join(log_lines))

    return paths["data_dictionary_csv"]


def write_all(datasets: dict) -> dict:
    return {name: write_dictionary(name, datasets) for name in datasets}


if __name__ == "__main__":
    write_all(config.DATASETS)
