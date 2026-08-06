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
