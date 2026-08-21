"""Stage 4 (build brief Step 7): basic imputation on the cleaned dataset,
scoped to the same five named variables as the problem inventory -- sex,
age, hours worked, industry (ISIC), occupation (ISCO). Reads
Outputs/typed/<name>_cleaned.parquet (written by clean.py); writes
Outputs/typed/<name>_imputed.parquet plus a before/after imputation log.

Method chosen per variable, per Section 3.3 of the brief ("pick the method
that fits the variable type and the missingness pattern; brief
justification is enough") -- every number below was checked against the
actual cleaned data, not assumed:

- Age (q1_04 ind / q7_06 emig): median. Both are numeric with a real right
  skew after clean.py's -1 sentinel correction (ind: 12 missing, mean 30.7
  vs median 26.0, skew 0.52; emig: 28 missing, mean 39.7 vs median 38.0,
  skew 0.29). The brief calls out median for "numeric variables with skew
  or outliers"; using it for both keeps the two age variables consistent
  with each other too.
- Hours worked, main job (q3_03) and the seven daily hours columns
  (q3_07_1..7): median, restricted to respondents who actually have a
  main job (q3_16 not null). These are the genuinely incidental gaps left
  by clean.py's sentinel corrections (88 rows for q3_03, 14-15 per daily
  column) -- q3_03 itself is confirmed skewed (skew 0.25, mean 44.5 vs
  median 40) with a known top-code history, so median over mean here too.
- Hours worked, other job (q3_08): median, restricted to the much
  narrower population that actually has a second job (q3_01 == "Yes",
  n=163) -- q3_08 only applies there. Naively imputing over the full
  4,789-row "has a main job" population (like q3_03) would have
  manufactured 4,626 fake values for people who were never asked the
  question; scoped correctly, only 1 row is genuinely incidental.
- Hours worked, other job (q3_04): LEFT MISSING. 100% of its missingness
  (13,690 of 13,853 rows) is structural (gated by q3_01 == "Yes", per
  config.SKIP_PATTERNS) -- confirmed 0 incidental gaps among the 163 rows
  the question actually applies to. Nothing to impute.
- q3_05 / q3_09 / q3_10 (all-jobs usual/actual totals): not independently
  imputed -- they are derived fields (clean.py's recompute_derived_hours()
  recalculates them from their own components, and q3_05 is itself
  structurally gated by q3_01 the same way q3_04 is). Re-run here, after
  the base components above are imputed, so the derived totals reflect
  the now-more-complete data instead of carrying stale NaNs.
- Industry (isic_code) / Occupation (isco_code): LEFT MISSING. Confirmed
  structural -- missingness (9,064 rows) exactly matches the population
  with no main job (q3_16 null). Imputing a job classification for people
  never asked about a job would invent data, not fill a gap.
- Sex (q1_03): 0 missing in the cleaned data -- nothing to impute.

Every imputed value is tracked in a companion `<column>_imputed` boolean
column, so the report step (build brief Step 10 / brief Section 4.3's
required observed-vs-imputed chart) can identify which rows were touched
without re-deriving it.
"""

from pathlib import Path

import pandas as pd

import config
from clean import recompute_derived_hours

_MAIN_JOB_DAILY_HOURS_COLUMNS = [f"q3_07_{i}" for i in range(1, 8)]


def impute_median(df: pd.DataFrame, column: str, population_mask: pd.Series = None) -> tuple:
    """Fill NaN in `column` with its own median, restricted to rows where
    `population_mask` is True (the subpopulation the variable actually
    applies to -- pass None if it applies to everyone). Rows outside the
    mask are left untouched: that's structural missingness, not incidental,
    and imputing it would invent an answer to a question that was never
    asked. Rounded to the nearest whole number before filling, since every
    column imputed here is a whole-number nullable Int type (years, hours)
    and an even-count median can otherwise land on a .5 that the column's
    dtype can't hold. Adds a `<column>_imputed` boolean flag column.
    Returns (df, n_imputed, fill_value)."""
    df = df.copy()
    series = df[column].astype("Float64")
    missing = series.isna()
    mask = missing if population_mask is None else (missing & population_mask)

    fill_value = int(round(series.median()))
    flag_col = f"{column}_imputed"
    df[flag_col] = False
    df.loc[mask, flag_col] = True
    df.loc[mask, column] = fill_value

    return df, int(mask.sum()), fill_value


def impute_ind(df: pd.DataFrame) -> tuple:
    """Runs every imputation decision documented in the module docstring
    for `ind`, in order, then re-derives the hours totals that depend on
    the now-imputed components. Returns (df, log_lines)."""
    log_lines = []

    df, n, fill = impute_median(df, "q1_04", population_mask=None)
    log_lines.append(f"Age (q1_04): median imputation, {n} row(s) filled with {fill}")

    has_main_job = df["q3_16"].notna()
    df, n, fill = impute_median(df, "q3_03", population_mask=has_main_job)
    log_lines.append(f"Hours worked, main job (q3_03): median imputation, {n} row(s) filled with {fill}")

    for col in _MAIN_JOB_DAILY_HOURS_COLUMNS:
        df, n, fill = impute_median(df, col, population_mask=has_main_job)
        log_lines.append(f"Hours worked, daily main job ({col}): median imputation, {n} row(s) filled with {fill}")

    has_second_job = df["q3_01"] == "Yes"
    df, n, fill = impute_median(df, "q3_08", population_mask=has_second_job)
    log_lines.append(f"Hours worked, other job actual (q3_08): median imputation, {n} row(s) filled with {fill}")

    n_q304_missing = int(df["q3_04"].isna().sum())
    n_q304_incidental = int(df.loc[has_second_job, "q3_04"].isna().sum())
    log_lines.append(
        f"Hours worked, other job usual (q3_04): LEFT MISSING -- {n_q304_missing} missing total, "
        f"{n_q304_incidental} of those among the {int(has_second_job.sum())} rows the question actually "
        "applies to (100% structural, gated by q3_01 == 'Yes'); nothing incidental to impute"
    )

    df, recompute_changed = recompute_derived_hours(df, "ind")
    for field, n_changed in recompute_changed.items():
        log_lines.append(f"Re-derived {field} from imputed components: {n_changed} value(s) changed")

    n_isic_missing = int(df["isic_code"].isna().sum())
    n_isco_missing = int(df["isco_code"].isna().sum())
    n_no_main_job = int((~has_main_job).sum())
    log_lines.append(
        f"Industry (isic_code): LEFT MISSING -- {n_isic_missing} missing, exactly matches the "
        f"{n_no_main_job} rows with no main job (fully structural, confirmed in problem_inventory.py); "
        "imputing a job classification for people never asked about a job would invent data"
    )
    log_lines.append(
        f"Occupation (isco_code): LEFT MISSING -- {n_isco_missing} missing, same structural pattern as isic_code"
    )

    n_sex_missing = int(df["q1_03"].isna().sum())
    log_lines.append(f"Sex (q1_03): {n_sex_missing} missing -- nothing to impute")

    return df, log_lines


def impute_emig(df: pd.DataFrame) -> tuple:
    """emig's assigned scope is age only -- the hours/ISIC/ISCO variables
    don't exist in this module. Returns (df, log_lines)."""
    df, n, fill = impute_median(df, "q7_06", population_mask=None)
    log_lines = [f"Age (q7_06): median imputation, {n} row(s) filled with {fill}"]
    return df, log_lines


def impute_dataset(name: str, datasets: dict) -> Path:
    """Runs the imputation stage for one dataset. Reads
    Outputs/typed/<name>_cleaned.parquet -- run clean.py first."""
    paths = datasets[name]
    df = pd.read_parquet(paths["cleaned"])
    log_lines = [f"Imputation: {name}", f"Rows: {len(df)}", ""]

    if name == "ind":
        df, stage_lines = impute_ind(df)
    else:
        df, stage_lines = impute_emig(df)
    log_lines.extend(stage_lines)

    df.to_parquet(paths["imputed"], index=False)
    log_lines.append(f"\nImputed dataset written to {paths['imputed'].name}")

    paths["imputation_log"].write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print("\n".join(log_lines))

    return paths["imputed"]


def impute_all(datasets: dict) -> dict:
    return {name: impute_dataset(name, datasets) for name in datasets}


if __name__ == "__main__":
    impute_all(config.DATASETS)
