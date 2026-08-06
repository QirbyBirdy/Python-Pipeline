"""Stage 1: read raw GLFS CSVs, validate against their dictionaries, verify
row/column counts against the source documentation, and write a
dtype-stable working copy to Outputs/interim/*.parquet."""

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


def verify_counts(name: str, df: pd.DataFrame, expected_counts: dict) -> tuple:
    """Compare observed row/household counts against the source documentation.
    Returns (log_lines, ok) -- ok is False if a documented expectation was violated."""
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
            "No documented expected count for this dataset in the methodological "
            "report -- counts above are logged for the record only."
        )
        return lines, True

    rows_match = n_rows == expected["individuals"]
    hh_match = n_households == expected["households"]
    lines.append(
        f"Expected individuals (methodological report, p.3): {expected['individuals']} "
        f"-- {'MATCH' if rows_match else 'MISMATCH'}"
    )
    lines.append(
        f"Expected households (methodological report, p.3): {expected['households']} "
        f"-- {'MATCH' if hh_match else 'MISMATCH'}"
    )
    return lines, rows_match and hh_match


def ingest(name: str, datasets: dict, expected_counts: dict) -> Path:
    df = load_dataset(name, datasets)

    log_lines, counts_ok = verify_counts(name, df, expected_counts)
    datasets[name]["ingest_log"].write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    if not counts_ok:
        raise ValueError(
            f"Row/household count mismatch for '{name}' vs. source documentation -- "
            f"see {datasets[name]['ingest_log']} for details"
        )

    out_path = datasets[name]["interim"]
    df.to_parquet(out_path, index=False)
    return out_path


def ingest_all(datasets: dict, expected_counts: dict) -> dict:
    return {name: ingest(name, datasets, expected_counts) for name in datasets}
