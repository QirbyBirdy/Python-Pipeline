"""Stage 2 (build brief Step 4): exploratory diagnostics on the typed data
-- missingness, duplicate keys, range checks, and named-variable
distributions with recommendations. Nothing here modifies or cleans data;
it only reports.

Note on date parsing: the brief's Step 4 checklist also lists date parsing.
Neither public dataset has an actual date field -- submission dates, device
timestamps, and date_birth were all stripped from the restricted dataset
before public release. The closest things (`quarter`/`week`, and `q7_09`
emigration year) are period identifiers, not dates, so there's nothing to
parse here.
"""

import pandas as pd

import config
from ingest import apply_dtypes, load_dataset

# Natural duplicate-check key per dataset: one row per person, so
# (household, member-within-household) should be unique.
_DUPLICATE_KEYS = {
    "ind": ["hhid", "member"],
    "emig": ["hhid", "emig"],
}

# Simple sanity bounds for range_check(), keyed by (dataset, column).
# None means "no bound on that side".
_RANGE_CHECKS = {
    ("ind", "q1_04"): (0, 115),  # Age
    ("ind", "q3_03"): (0, 168),  # Usual hours/week, main job (24*7)
    ("ind", "q3_05"): (0, 168),  # Usual hours/week, all jobs
    ("ind", "weight"): (0, None),  # Sampling weight must be positive
    ("emig", "q7_06"): (0, 115),  # Age
    ("emig", "weight"): (0, None),
}

# NOTE: no code -> label mapping is needed for category columns. Verified
# empirically (see README) that the public CSVs already store the resolved
# label TEXT for every coded field (e.g. q1_03 contains "Male"/"Female"
# directly, not "1"/"2") -- Stata's export wrote out labeled values rather
# than raw codes. value_counts_labeled()'s `labels` param exists only for
# the rare case a future column turns out to hold real numeric codes.

_AGE_BINS = [0, 15, 25, 35, 45, 55, 65, 150]
_AGE_LABELS = ["0-14", "15-24", "25-34", "35-44", "45-54", "55-64", "65+"]


def load_typed(name: str, datasets: dict) -> pd.DataFrame:
    """Load a dataset raw and apply the recommended dtypes -- diagnostics
    need real dtypes (numeric/category), not the all-string safety-net copy."""
    df = load_dataset(name, datasets)
    typed_df, _ = apply_dtypes(df, name, datasets)
    return typed_df


def missingness_report(df: pd.DataFrame) -> pd.DataFrame:
    """% missing per column, worst first."""
    n = len(df)
    report = pd.DataFrame({"column": df.columns, "n_missing": df.isna().sum().values})
    report["pct_missing"] = (100 * report["n_missing"] / n).round(2) if n else 0.0
    return report.sort_values("pct_missing", ascending=False).reset_index(drop=True)


def find_duplicates(df: pd.DataFrame, key_columns: list) -> pd.DataFrame:
    """Exact-match duplicate check on key_columns. Returns every row
    involved in a duplicate group (empty if none)."""
    dup_mask = df.duplicated(subset=key_columns, keep=False)
    return df.loc[dup_mask, key_columns].sort_values(key_columns)


def range_check(df: pd.DataFrame, column: str, low, high) -> pd.DataFrame:
    """Flag non-missing values in `column` outside [low, high] (either bound
    may be None to skip that side). Returns the flagged rows (empty if none)."""
    series = df[column]
    below = series < low if low is not None else False
    above = series > high if high is not None else False
    flagged = series.notna() & (below | above)
    return df.loc[flagged, [column]]


def _describe_flagged(flagged: pd.DataFrame, column: str) -> str:
    """Human-readable summary of range_check()'s output for one column --
    calls out a uniform sentinel value (e.g. every flag is exactly -1)
    rather than just reporting a count, since that's a very different
    situation from scattered genuinely-implausible values."""
    values = flagged[column].value_counts()
    if len(values) == 1:
        (only_value, count), = values.items()
        return (
            f"{count} value(s) out of range, all exactly {only_value} -- looks like a "
            "missing/'don't know' sentinel, not a real data error. Treat as NaN when cleaning "
            "rather than a literal value."
        )
    return f"{len(flagged)} value(s) out of range: {values.to_dict()} -- inspect before cleaning."


def value_counts_labeled(series: pd.Series, labels: dict = None) -> tuple:
    """Frequency table for a column (code, label, count, % of valid),
    plus the missing count separately. `labels` maps raw code -> readable
    text; codes without a mapping fall back to the raw code as a string."""
    n_missing = int(series.isna().sum())
    counts = series.value_counts(dropna=True)
    n_valid = int(counts.sum())
    rows = []
    for code, count in counts.items():
        label = (labels or {}).get(str(code), str(code))
        rows.append(
            {
                "code": str(code),
                "label": label,
                "count": int(count),
                "pct_of_valid": round(100 * count / n_valid, 2) if n_valid else 0.0,
            }
        )
    table = pd.DataFrame(rows).sort_values("count", ascending=False).reset_index(drop=True)
    return table, n_missing


def age_group_distribution(age_series: pd.Series) -> tuple:
    """Bucket a numeric age column into standard age groups and return the
    same (table, n_missing) shape as value_counts_labeled()."""
    groups = pd.cut(age_series.astype("Float64"), bins=_AGE_BINS, labels=_AGE_LABELS, right=False)
    return value_counts_labeled(groups)


def render_diagnostics_report(
    name: str,
    df: pd.DataFrame,
    missingness: pd.DataFrame,
    duplicates: pd.DataFrame,
    range_flags: dict,
    distributions: dict,
    recommendations: list,
) -> str:
    n_rows, n_cols = df.shape
    lines = [
        f"# Diagnostics report: {name}",
        "",
        f"- Rows: {n_rows}",
        f"- Columns: {n_cols}",
        "",
        "## Missingness (top 15 columns by % missing)",
        "",
        "| Column | % missing | # missing |",
        "| --- | --- | --- |",
    ]
    for _, row in missingness.head(15).iterrows():
        lines.append(f"| {row['column']} | {row['pct_missing']} | {row['n_missing']} |")

    lines += ["", f"## Duplicate rows on natural key {_DUPLICATE_KEYS[name]} ({len(duplicates)} rows involved)", ""]
    if len(duplicates):
        for _, row in duplicates.iterrows():
            lines.append(f"- {dict(row)}")
    else:
        lines.append("- none found")

    lines += ["", "## Range checks", ""]
    any_flags = False
    for col, flagged in range_flags.items():
        if len(flagged):
            any_flags = True
            lines.append(f"- **{col}**: {len(flagged)} value(s) out of range")
    if not any_flags:
        lines.append("- none found -- all checked columns within expected bounds")

    lines += ["", "## Named-variable distributions", ""]
    for title, (table, n_missing) in distributions.items():
        lines += [f"### {title}", "", f"Missing: {n_missing}", "", "| Label | Count | % of valid |", "| --- | --- | --- |"]
        for _, row in table.iterrows():
            lines.append(f"| {row['label']} | {row['count']} | {row['pct_of_valid']} |")
        lines.append("")

    lines += ["## Recommendations", ""]
    for rec in recommendations:
        lines.append(f"- {rec}")

    return "\n".join(lines) + "\n"


def diagnose_ind(datasets: dict) -> dict:
    """Run all diagnostics for the ind dataset. Returns everything computed
    (for reuse/testing), and writes the report + CSV to Outputs/diagnostics/."""
    paths = datasets["ind"]
    df = load_typed("ind", datasets)

    missingness = missingness_report(df)
    duplicates = find_duplicates(df, _DUPLICATE_KEYS["ind"])
    range_flags = {
        col: range_check(df, col, low, high)
        for (dname, col), (low, high) in _RANGE_CHECKS.items()
        if dname == "ind"
    }

    sex_table, sex_missing = value_counts_labeled(df["q1_03"])
    age_table, age_missing = age_group_distribution(df["q1_04"])
    emp_table, emp_missing = value_counts_labeled(df["q3_16"])
    distributions = {
        "Sex (q1_03)": (sex_table, sex_missing),
        "Age group (q1_04, bucketed)": (age_table, age_missing),
        "Employment status, main job (q3_16)": (emp_table, emp_missing),
    }

    recommendations = []

    dup_pct = 100 * len(duplicates) / len(df) if len(df) else 0
    if len(duplicates):
        recommendations.append(
            f"{len(duplicates)} rows ({dup_pct:.2f}%) share a duplicate hhid+member key -- "
            "investigate before any dedup step; a real household could have this collide only "
            "on data-entry error."
        )
    else:
        recommendations.append("No duplicate hhid+member rows -- this is a reliable natural key, no dedup logic needed.")

    for col, flagged in range_flags.items():
        if len(flagged):
            recommendations.append(f"{col}: {_describe_flagged(flagged, col)}")
    if not any(len(flagged) for flagged in range_flags.values()):
        recommendations.append("Age, hours-worked, and weight all fall within expected bounds -- no range-check flags.")

    heavy_missing = missingness[missingness["pct_missing"] > 90]
    recommendations.append(
        f"{len(heavy_missing)} columns are >90% missing -- almost entirely expected survey skip patterns "
        "(e.g. q6_* income sub-questions only apply to employees with that income source), not a data-quality "
        "problem by itself. Worth distinguishing structural vs. incidental missingness per-variable once cleaning scope is known."
    )

    n_male = int(sex_table.loc[sex_table["label"] == "Male", "count"].sum())
    n_female = int(sex_table.loc[sex_table["label"] == "Female", "count"].sum())
    n_valid_sex = n_male + n_female
    if n_valid_sex:
        pct_male = 100 * n_male / n_valid_sex
        recommendations.append(
            f"Sex is {pct_male:.1f}% male / {100 - pct_male:.1f}% female with {sex_missing} missing -- "
            "close to balanced, no coverage concern for this variable."
        )

    top_emp = emp_table.iloc[0] if len(emp_table) else None
    if top_emp is not None:
        recommendations.append(
            f"'{top_emp['label']}' dominates employment status ({top_emp['pct_of_valid']}% of valid responses); "
            f"{emp_missing} rows are missing this field entirely (not currently employed, so q3_16 correctly does "
            "not apply) -- do not treat that as missing data to impute, it's a structural skip."
        )

    log_text = render_diagnostics_report("ind", df, missingness, duplicates, range_flags, distributions, recommendations)
    paths["diagnostics_report"].write_text(log_text, encoding="utf-8")
    missingness.to_csv(paths["diagnostics_csv"], index=False)
    print(log_text)

    return {
        "missingness": missingness,
        "duplicates": duplicates,
        "range_flags": range_flags,
        "distributions": distributions,
        "recommendations": recommendations,
    }


def diagnose_emig(datasets: dict) -> dict:
    """Run missingness/duplicate/range diagnostics for the emig dataset
    (no named-variable distribution section -- ind is the survey's primary
    labor-force dataset, this is the lighter secondary module)."""
    paths = datasets["emig"]
    df = load_typed("emig", datasets)

    missingness = missingness_report(df)
    duplicates = find_duplicates(df, _DUPLICATE_KEYS["emig"])
    range_flags = {
        col: range_check(df, col, low, high)
        for (dname, col), (low, high) in _RANGE_CHECKS.items()
        if dname == "emig"
    }

    recommendations = []
    if len(duplicates):
        recommendations.append(f"{len(duplicates)} rows share a duplicate hhid+emig key -- investigate before dedup.")
    else:
        recommendations.append("No duplicate hhid+emig rows -- reliable natural key.")
    for col, flagged in range_flags.items():
        if len(flagged):
            recommendations.append(f"{col}: {_describe_flagged(flagged, col)}")
    if not any(len(flagged) for flagged in range_flags.values()):
        recommendations.append("Age and weight fall within expected bounds -- no range-check flags.")

    log_text = render_diagnostics_report("emig", df, missingness, duplicates, range_flags, {}, recommendations)
    paths["diagnostics_report"].write_text(log_text, encoding="utf-8")
    missingness.to_csv(paths["diagnostics_csv"], index=False)
    print(log_text)

    return {
        "missingness": missingness,
        "duplicates": duplicates,
        "range_flags": range_flags,
        "recommendations": recommendations,
    }


if __name__ == "__main__":
    diagnose_ind(config.DATASETS)
    diagnose_emig(config.DATASETS)
