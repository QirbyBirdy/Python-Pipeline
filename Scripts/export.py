"""Stage 6 (build brief Step 9 / Section 4.1): export the final dataset in
all four required formats -- .sav, .dta, .xlsx, .parquet. Reads
Outputs/typed/<name>_imputed.parquet (the fully cleaned *and* imputed
data -- build Step 7 runs before Step 9, and Section 4.1's "cleaned
dataset" phrase is read here as "the final processed dataset", matching
that order rather than re-exporting a pre-imputation snapshot).

Format-specific handling, verified against pyreadstat's actual behavior
before trusting it -- round-tripped a sample first (write then read back)
rather than assuming:

- .parquet: plain pandas.to_parquet(). No conversion needed; this is
  already the dataset's native working format.
- .xlsx: data on one sheet ("data"), the data dictionary
  (Scripts/data_dictionary.py, reused rather than rebuilt) on a second
  sheet ("data_dictionary") -- per the brief's Table 4 ("data on one
  sheet, data dictionary on a second sheet").
- .sav / .dta: pyreadstat. Confirmed by round-trip test that pyreadstat
  handles every pandas nullable dtype used in this pipeline (Int8/16/32/64,
  boolean, category, string) correctly on its own: nullable integers
  become float64 with real NaN preserved; category/string columns keep
  their text, with missing values round-tripping as an empty string
  rather than NaN -- the standard SPSS/Stata convention for missing
  string data (those formats have no string NaN), not a defect introduced
  here.

  Variable labels (`column_labels`) are attached for every column,
  reusing the exact same labels data_dictionary.py builds -- one source
  of truth, not a second copy that could drift from it.

  Value labels (`variable_value_labels`) are a numeric-variable-only
  feature in both formats. Our categorical columns already store resolved
  label TEXT, not numeric codes -- confirmed back in the diagnostics stage
  (dictionary CSVs only name a Stata *label-set*, e.g. "yesno"; the
  exported values are already "Male"/"Female" etc., never a code needing
  a lookup) -- so there is no code -> label mapping to preserve for them.
  The one place this genuinely applies: the ten (`ind`) / one (`emig`)
  `<column>_imputed` flag columns, recoded here from True/False to 1/0
  specifically so a real value-label pair can be attached
  ({0: "Not imputed", 1: "Imputed"}), which a plain boolean column can't
  carry in either format.

  Stata version is left at pyreadstat's default (15), matching the
  brief's own "Stata v15+ recommended for Unicode".
"""

import pandas as pd
import pyreadstat

import config
from data_dictionary import build_dictionary, column_labels


def _flag_columns_to_int(df: pd.DataFrame) -> tuple:
    """<column>_imputed: bool -> nullable Int8 (0/1), so a real value-label
    pair can be attached in the .sav/.dta writers below -- Stata and SPSS
    value labels are a numeric-variable feature, and a plain boolean
    column can't carry them in either format. Returns (df, value_labels)."""
    df = df.copy()
    flag_cols = [c for c in df.columns if c.endswith("_imputed")]
    value_labels = {}
    for col in flag_cols:
        df[col] = df[col].astype("Int8")
        value_labels[col] = {0: "Not imputed", 1: "Imputed"}
    return df, value_labels


def export_dataset(name: str, datasets: dict) -> dict:
    """Writes all four required formats for one dataset. Requires
    ingest.py -> clean.py -> impute.py to have already run. Returns
    {format: path}."""
    paths = datasets[name]
    df = pd.read_parquet(paths["imputed"])
    n_cols = len(df.columns)

    labels = column_labels(name, datasets, df.columns)
    dictionary_df = build_dictionary(name, datasets)

    log_lines = [f"Export: {name}", f"Rows: {len(df)}", f"Columns: {n_cols}", ""]

    df.to_parquet(paths["export_parquet"], index=False)
    log_lines.append(f".parquet -> {paths['export_parquet'].name}")

    with pd.ExcelWriter(paths["export_xlsx"], engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="data", index=False)
        dictionary_df.to_excel(writer, sheet_name="data_dictionary", index=False)
    log_lines.append(f".xlsx -> {paths['export_xlsx'].name} (sheets: data, data_dictionary)")

    df_labeled, value_labels = _flag_columns_to_int(df)

    pyreadstat.write_sav(df_labeled, str(paths["export_sav"]), column_labels=labels, variable_value_labels=value_labels)
    log_lines.append(f".sav -> {paths['export_sav'].name} (variable labels: {n_cols}, value labels: {len(value_labels)})")

    pyreadstat.write_dta(df_labeled, str(paths["export_dta"]), column_labels=labels, variable_value_labels=value_labels)
    log_lines.append(f".dta -> {paths['export_dta'].name} (variable labels: {n_cols}, value labels: {len(value_labels)})")

    # Verify: read every format back and confirm shape survives the round trip.
    for fmt, path, reader in [
        ("parquet", paths["export_parquet"], lambda p: pd.read_parquet(p)),
        ("xlsx", paths["export_xlsx"], lambda p: pd.read_excel(p, sheet_name="data")),
        ("sav", paths["export_sav"], lambda p: pyreadstat.read_sav(str(p))[0]),
        ("dta", paths["export_dta"], lambda p: pyreadstat.read_dta(str(p))[0]),
    ]:
        back = reader(path)
        ok = back.shape == df.shape
        log_lines.append(f"Round-trip check ({fmt}): shape {back.shape} vs original {df.shape} -- {'OK' if ok else 'MISMATCH'}")

    paths["export_log"].write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print("\n".join(log_lines))

    return {
        "parquet": paths["export_parquet"],
        "xlsx": paths["export_xlsx"],
        "sav": paths["export_sav"],
        "dta": paths["export_dta"],
    }


def export_all(datasets: dict) -> dict:
    return {name: export_dataset(name, datasets) for name in datasets}


if __name__ == "__main__":
    export_all(config.DATASETS)
