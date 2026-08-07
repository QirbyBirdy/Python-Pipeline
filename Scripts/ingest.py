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


# Stata storage type -> recommended pandas dtype once a column is actually
# cleaned. Advisory only; nothing in this module applies a conversion.
_NUMERIC_TYPE_ADVICE = {
    "byte": "Int8 (nullable)",
    "int": "Int32 (nullable)",
    "long": "Int64 (nullable) -- used here for monetary amounts, can be large",
    "float": "float64",
    "double": "float64",
}


def recommend_dtypes(name: str, datasets: dict) -> pd.DataFrame:
    """For every column, combine the dictionary's declared Stata type and
    whether it has a documented choices label-set into a recommended
    pandas dtype and a plain-language reason."""
    dictionary = load_dictionary(name, datasets)

    def _recommend(row):
        stata_type = row["type"]
        has_choices = isinstance(row["choices"], str) and row["choices"].strip() != ""
        if stata_type.startswith("str"):
            width = int(stata_type.replace("str", ""))
            if width > 20:
                return "string", "free-text field -- no coded companion; out of scope to standardize under 'basic methods only'"
            return "string", "short code/ID field -- leading characters can matter (e.g. region '01'); never coerce to a number"
        if stata_type == "byte" and has_choices:
            return "category", f"coded categorical response (choices label-set: '{row['choices']}')"
        if stata_type in _NUMERIC_TYPE_ADVICE:
            return _NUMERIC_TYPE_ADVICE[stata_type], "numeric response (count, amount, or year) -- no documented choices label-set"
        return "string", "undeclared/unrecognized Stata type -- inspect manually"

    recs = dictionary.apply(_recommend, axis=1, result_type="expand")
    recs.columns = ["recommended_dtype", "reason"]
    return pd.concat([dictionary[["column", "description", "type", "choices"]], recs], axis=1)


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


if __name__ == "__main__":
    for dataset_name in config.DATASETS:
        print(f"=== {dataset_name} ===")
        out_path = ingest(dataset_name, config.DATASETS, config.EXPECTED_COUNTS)
        print(f"-> {out_path}\n")
