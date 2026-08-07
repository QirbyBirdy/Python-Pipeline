"""Load the GLFS raw datasets and provide basic metadata-exploration
helpers: field lists, dtypes, dtype recommendations, and row/household
count verification against the source methodological report.

No cleaning or value transformation happens here -- dtype recommendations
are advisory only; the loaded DataFrame keeps every column as a string.
"""

from pathlib import Path

import pandas as pd

import config


def load_dictionary(name: str, datasets: dict) -> pd.DataFrame:
    """Read a dataset's data dictionary: column, description, Stata type, choices label-set."""
    return pd.read_csv(datasets[name]["dictionary"])


def load_dataset(name: str, datasets: dict) -> pd.DataFrame:
    """Read a dataset's raw CSV. Every column is read as a string -- GLFS
    data is almost entirely coded/categorical, so nothing is silently
    coerced to a number. Use recommend_dtypes() for what each column should
    probably become once cleaning starts."""
    paths = datasets[name]
    df = pd.read_csv(paths["csv"], dtype=str)
    dictionary = load_dictionary(name, datasets)

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


def get_fields(df: pd.DataFrame) -> list:
    """Return the list of column names in a loaded dataset."""
    return list(df.columns)


def get_num_fields(df: pd.DataFrame) -> int:
    """Return how many columns a loaded dataset has."""
    return len(df.columns)


def get_dtypes(df: pd.DataFrame) -> pd.Series:
    """Return the current pandas dtype of every column (all 'object',
    since load_dataset reads everything as a string)."""
    return df.dtypes


def get_documented_types(name: str, datasets: dict) -> pd.Series:
    """Return the dictionary's declared Stata `type` for every column,
    indexed by column name (e.g. byte, str13, double, long)."""
    dictionary = load_dictionary(name, datasets)
    return dictionary.set_index("column")["type"]


# Stata storage type -> recommended pandas dtype. Single source of truth
# for both the advisory recommend_dtypes() report and the actual conversion
# in apply_dtypes() -- the token returned here is a literal dtype name
# usable with .astype() (numeric tokens go through pd.to_numeric first).
_NUMERIC_TYPE_MAP = {
    "byte": ("Int8", "small numeric count (age, hours/week, block, week)"),
    "int": ("Int32", "larger numeric (panel ID, quarter, total hours, emigration year)"),
    "long": ("Int64", "monetary amount -- can be large"),
    "float": ("float64", "weight or geo-coordinate"),
    "double": ("float64", "weight or geo-coordinate"),
}


def _dtype_for_stata_type(stata_type: str, has_choices: bool) -> tuple:
    """Return (pandas_dtype_token, reason) for one column's declared Stata type."""
    if stata_type.startswith("str"):
        width = int(stata_type.replace("str", ""))
        if width > 20:
            return "string", "free-text field -- no coded companion; out of scope to standardize under 'basic methods only'"
        return "string", "short code/ID field -- leading characters can matter (e.g. region '01'); never coerce to a number"
    if stata_type == "byte" and has_choices:
        return "category", "coded categorical response"
    if stata_type in _NUMERIC_TYPE_MAP:
        return _NUMERIC_TYPE_MAP[stata_type]
    return "string", "undeclared/unrecognized Stata type -- inspect manually"


def recommend_dtypes(name: str, datasets: dict) -> pd.DataFrame:
    """For every column, combine the dictionary's declared Stata type and
    whether it has a documented choices label-set into a recommended
    pandas dtype and a plain-language reason."""
    dictionary = load_dictionary(name, datasets)

    def _recommend(row):
        has_choices = isinstance(row["choices"], str) and row["choices"].strip() != ""
        dtype_token, reason = _dtype_for_stata_type(row["type"], has_choices)
        if dtype_token == "category":
            reason = f"{reason} (choices label-set: '{row['choices']}')"
        return dtype_token, reason

    recs = dictionary.apply(_recommend, axis=1, result_type="expand")
    recs.columns = ["recommended_dtype", "reason"]
    return pd.concat([dictionary[["column", "description", "type", "choices"]], recs], axis=1)


def apply_dtypes(df: pd.DataFrame, name: str, datasets: dict) -> tuple:
    """Apply recommend_dtypes()'s recommendations to a loaded (all-string)
    DataFrame. Returns (typed_df, coercion_report): typed_df is a new
    DataFrame (the input is not modified in place), and coercion_report has
    one row per column recording the dtype applied and how many values
    became NaN purely because of the conversion -- i.e. values that were
    present in the raw string data but didn't parse, not values that were
    already missing/blank."""
    dictionary = load_dictionary(name, datasets)
    typed_df = df.copy()
    report_rows = []

    for _, row in dictionary.iterrows():
        col = row["column"]
        has_choices = isinstance(row["choices"], str) and row["choices"].strip() != ""
        dtype_token, _ = _dtype_for_stata_type(row["type"], has_choices)

        series = typed_df[col]
        n_missing_before = int(series.isna().sum())

        if dtype_token in ("category", "string"):
            typed_df[col] = series.astype(dtype_token)
            n_new_na = 0
        else:
            numeric = pd.to_numeric(series, errors="coerce")
            n_new_na = int(numeric.isna().sum()) - n_missing_before
            typed_df[col] = numeric.astype(dtype_token)

        report_rows.append(
            {
                "column": col,
                "dtype_applied": dtype_token,
                "n_missing_before": n_missing_before,
                "n_new_na_from_coercion": n_new_na,
            }
        )

    return typed_df, pd.DataFrame(report_rows)


def render_coercion_report(name: str, coercion_report: pd.DataFrame) -> str:
    """Render apply_dtypes()'s coercion_report as a markdown summary,
    per the brief's requirement to 'report columns where coercion created NAs'."""
    flagged = coercion_report[coercion_report["n_new_na_from_coercion"] > 0]
    lines = [
        f"# Dtype coercion report: {name}",
        "",
        f"- Columns converted: {len(coercion_report)}",
        f"- Columns where coercion introduced new NaNs: {len(flagged)}",
        "",
        "| Column | Dtype applied | Missing before | New NaN from coercion |",
        "| --- | --- | --- | --- |",
    ]
    for _, row in coercion_report.iterrows():
        lines.append(
            f"| {row['column']} | {row['dtype_applied']} | {row['n_missing_before']} | "
            f"{row['n_new_na_from_coercion']} |"
        )
    return "\n".join(lines) + "\n"


def verify_counts(name: str, df: pd.DataFrame, expected_counts: dict) -> tuple:
    """Compare observed row/household counts against the source
    documentation (config.EXPECTED_COUNTS). Returns (log_lines, ok)."""
    n_rows, n_cols = df.shape
    n_households = df["hhid"].nunique()
    lines = [
        f"Dataset: {name}",
        f"Rows loaded: {n_rows}",
        f"Columns loaded: {n_cols}",
        f"Unique households (hhid): {n_households}",
    ]

    expected = expected_counts.get(name)
    if expected is None:
        lines.append(
            "No documented expected count for this dataset -- logged for the record only."
        )
        return lines, True

    rows_match = n_rows == expected["individuals"]
    hh_match = n_households == expected["households"]
    lines.append(
        f"Expected individuals: {expected['individuals']} -- {'MATCH' if rows_match else 'MISMATCH'}"
    )
    lines.append(
        f"Expected households: {expected['households']} -- {'MATCH' if hh_match else 'MISMATCH'}"
    )
    return lines, rows_match and hh_match


def ingest(name: str, datasets: dict, expected_counts: dict) -> Path:
    """Load, verify, and cache one dataset as interim parquet. Returns the output path."""
    df = load_dataset(name, datasets)

    log_lines, counts_ok = verify_counts(name, df, expected_counts)
    datasets[name]["ingest_log"].write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print("\n".join(log_lines))
    if not counts_ok:
        raise ValueError(
            f"Row/household count mismatch for '{name}' -- see "
            f"{datasets[name]['ingest_log']} for details"
        )

    out_path = datasets[name]["interim"]
    df.to_parquet(out_path, index=False)
    return out_path


def ingest_all(datasets: dict, expected_counts: dict) -> dict:
    return {name: ingest(name, datasets, expected_counts) for name in datasets}


def type_dataset(name: str, datasets: dict) -> Path:
    """Load the raw dataset fresh, apply recommend_dtypes()'s conversions,
    write the typed result to Outputs/typed/<name>_typed.parquet, and log
    the coercion report. The raw interim parquet from ingest() is untouched
    -- this is a separate, derived output."""
    df = load_dataset(name, datasets)
    typed_df, coercion_report = apply_dtypes(df, name, datasets)

    log_text = render_coercion_report(name, coercion_report)
    datasets[name]["dtype_log"].write_text(log_text, encoding="utf-8")
    print(log_text)

    out_path = datasets[name]["typed"]
    typed_df.to_parquet(out_path, index=False)
    return out_path


def type_all(datasets: dict) -> dict:
    return {name: type_dataset(name, datasets) for name in datasets}


if __name__ == "__main__":
    for dataset_name in config.DATASETS:
        print(f"=== {dataset_name}: ingest ===")
        interim_path = ingest(dataset_name, config.DATASETS, config.EXPECTED_COUNTS)
        print(f"-> {interim_path}\n")

        print(f"=== {dataset_name}: apply dtypes ===")
        typed_path = type_dataset(dataset_name, config.DATASETS)
        print(f"-> {typed_path}\n")
