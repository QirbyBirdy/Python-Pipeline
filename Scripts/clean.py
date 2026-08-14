"""Stage 3 (build brief Step 6): the actual value-changing cleaning
operations -- exact-duplicate removal, rule-based validation (flag or
correct, per CLEANING_PLAN.md Part 4), value-mapping application, and
ISIC-section / ISCO-major-group classification. Reads the typed parquet
written by ingest.py; writes a cleaned parquet, a cleaning log, and a
flagged-for-review CSV per dataset.

Every correction this module makes is logged with a before/after count.
Only one correction happens without a human review step first: the
verified -1 "don't know" age sentinel -> NaN (see diagnose.py's
_describe_flagged, which confirmed every range-check flag on age was
exactly -1). Everything else here is flag-only.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

import config

_ID_COLUMNS = {"ind": ["hhid", "member"], "emig": ["hhid", "emig"]}
_AGE_COLUMNS = {"ind": "q1_04", "emig": "q7_06"}

# Columns where 99 is a verified top-code/sentinel, not a literal value.
# Evidence (checked across every hours-related column before adding any of
# these): q3_03 has 88 values of exactly 99, with every other value capping
# at 98 -- a classic "99 or more" top-code. q3_05 has 6 (matching the
# usual_hours_mismatch flags). q3_04/q3_08/q3_09/q3_10/q3_07_1..7 all have
# ZERO occurrences of 99 despite going as high as 168 -- confirms this is
# specific to these two "usual hours" fields, not a general hours sentinel.
_HOURS_SENTINEL_COLUMNS = {"ind": ["q3_03", "q3_05"], "emig": []}

_FLAGGED_COLUMNS = ["hhid", "id2", "rule_name", "detail"]


def drop_exact_duplicates(df: pd.DataFrame, key_columns: list) -> tuple:
    """Exact-match dedup on key_columns, keeping the first occurrence.
    Returns (deduped_df, n_dropped)."""
    n_before = len(df)
    deduped = df.drop_duplicates(subset=key_columns, keep="first").copy()
    return deduped, n_before - len(deduped)


def correct_age_sentinel(df: pd.DataFrame, name: str) -> tuple:
    """The one auto-correction this module makes: age == -1 -> NaN.
    Defensible because diagnose.py's range check already confirmed every
    out-of-range age value is exactly -1 (a 'don't know' sentinel), not a
    scattered set of implausible values. Returns (df, n_corrected)."""
    col = _AGE_COLUMNS[name]
    df = df.copy()
    mask = df[col] == -1
    n_corrected = int(mask.sum())
    df.loc[mask, col] = pd.NA
    return df, n_corrected


def correct_hours_sentinel(df: pd.DataFrame, name: str) -> tuple:
    """The second verified auto-correction: 99 -> NaN in q3_03/q3_05 only
    (see _HOURS_SENTINEL_COLUMNS for the evidence). Returns
    (df, {column: n_corrected})."""
    df = df.copy()
    corrected = {}
    for col in _HOURS_SENTINEL_COLUMNS[name]:
        mask = df[col] == 99
        corrected[col] = int(mask.sum())
        df.loc[mask, col] = pd.NA
    return df, corrected


def _build_flags(df: pd.DataFrame, name: str, mask: pd.Series, rule_name: str, detail: pd.Series) -> pd.DataFrame:
    """Common shape for every flagged-row output: household + person ID,
    which rule flagged it, and a human-readable detail string."""
    id_cols = _ID_COLUMNS[name]
    flagged = df.loc[mask, id_cols].copy()
    flagged.columns = ["hhid", "id2"]
    flagged["rule_name"] = rule_name
    flagged["detail"] = detail[mask].values
    return flagged


def check_usual_hours_consistency(df: pd.DataFrame) -> pd.DataFrame:
    """q3_05 (total usual hours, all jobs) should ~= q3_03 (main job) +
    q3_04 (other jobs), allowing 1 hour of rounding slack. Flag only --
    which of the two conflicting numbers is 'right' isn't something a
    script can decide."""
    main = df["q3_03"].astype("Float64").fillna(0)
    other = df["q3_04"].astype("Float64").fillna(0)
    total = df["q3_05"].astype("Float64")
    expected = main + other
    diff = (expected - total).abs()
    mask = df["q3_05"].notna() & (diff > 1)
    detail = "q3_03+q3_04=" + expected.astype(str) + " vs q3_05=" + total.astype(str)
    return _build_flags(df, "ind", mask, "usual_hours_mismatch", detail)


def check_daily_hours_consistency(df: pd.DataFrame) -> pd.DataFrame:
    """q3_09 (total actual hours, main job, last 7 days) should ~= the sum
    of the seven daily columns q3_07_1..q3_07_7, allowing 1 hour slack."""
    day_cols = [f"q3_07_{i}" for i in range(1, 8)]
    daily_sum = sum(df[c].astype("Float64").fillna(0) for c in day_cols)
    total = df["q3_09"].astype("Float64")
    diff = (daily_sum - total).abs()
    mask = df["q3_09"].notna() & (diff > 1)
    detail = "daily_sum=" + daily_sum.astype(str) + " vs q3_09=" + total.astype(str)
    return _build_flags(df, "ind", mask, "daily_hours_mismatch", detail)


def check_employment_skip_logic(df: pd.DataFrame) -> pd.DataFrame:
    """If q2_04/q2_05/q2_07/q2_10 are all 'No' (not employed, no business,
    no unpaid family work, not temporarily absent), job-detail fields
    (isco_code) should be empty. A violation means either a genuine data
    issue or a more complex q3_16 gate than modeled -- flag either way."""
    not_employed = (
        (df["q2_04"] == "No") & (df["q2_05"] == "No") & (df["q2_07"] == "No") & (df["q2_10"] == "No")
    )
    mask = not_employed & df["isco_code"].notna()
    detail = pd.Series("not employed per q2_04/q2_05/q2_07/q2_10 but isco_code is filled", index=df.index)
    return _build_flags(df, "ind", mask, "employment_skip_violation", detail)


def flag_monetary_outliers(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """IQR-based outlier flag (1.5x IQR, the conventional default) for
    every column in config.MONETARY_COLUMNS. Flag only -- never dropped or
    altered ("flag; do not silently drop", per the brief)."""
    frames = []
    for col in config.MONETARY_COLUMNS[name]:
        if col not in df.columns:
            continue
        series = df[col].astype("Float64")
        valid = series.dropna()
        if len(valid) < 10:
            continue
        q1, q3 = valid.quantile(0.25), valid.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mask = series.notna() & ((series < low) | (series > high))
        if not mask.any():
            continue
        detail = pd.Series(
            f"{col}=" + series.astype(str) + f" outside IQR bounds [{low:.0f}, {high:.0f}]", index=df.index
        )
        frames.append(_build_flags(df, name, mask, f"monetary_outlier_{col}", detail))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=_FLAGGED_COLUMNS)


def apply_validation_rules(df: pd.DataFrame, name: str) -> tuple:
    """Runs every flag-only rule for `name` and concatenates the results.
    Returns (flagged_rows,) -- does not touch df; corrections happen
    separately via correct_age_sentinel()."""
    frames = []
    if name == "ind":
        frames.append(check_usual_hours_consistency(df))
        frames.append(check_daily_hours_consistency(df))
        frames.append(check_employment_skip_logic(df))
    frames.append(flag_monetary_outliers(df, name))
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=_FLAGGED_COLUMNS)


def apply_value_mapping(df: pd.DataFrame, column: str, mapping: dict) -> tuple:
    """Apply a hand-built {from_value: to_value} mapping to one column
    (see CLEANING_PLAN.md Part 5 -- mapping is built from reviewing
    diagnose.py's find_near_duplicate_values() output, not guessed).
    Returns (df, n_rows_affected)."""
    if not mapping or column not in df.columns:
        return df, 0
    df = df.copy()
    series = df[column].astype(str)
    matched = series.isin(mapping.keys())
    n_affected = int(matched.sum())
    if n_affected:
        df.loc[matched, column] = series[matched].map(mapping)
    return df, n_affected


def build_consolidation_mapping(near_duplicates: pd.DataFrame, min_similarity: float = 0.98) -> dict:
    """Cluster near-duplicate free-text values (>= min_similarity) per
    column with union-find, then map every value in a cluster to the
    cluster's most frequent value. Returns {column: {from_value: to_value}}.

    0.98 is a conservative, evidence-based threshold (see CLEANING_PLAN.md
    Part 5 / README): checked the actual pairs at 0.98 by eye -- all typo/
    spacing/pluralization variants of the same real answer (e.g. "GOLD
    SMITH" / "GOLDSMITH", "SHOP OWNER" / "SHOPOWNER"), unlike the noisier
    0.90-0.95 band which mixes in genuinely different short answers."""
    mappings = {}
    close_pairs = near_duplicates[near_duplicates["similarity"] >= min_similarity]
    for column, group in close_pairs.groupby("column"):
        parent = {}

        def find(x):
            while parent.get(x, x) != x:
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        counts = {}
        for _, row in group.iterrows():
            parent.setdefault(row["value_a"], row["value_a"])
            parent.setdefault(row["value_b"], row["value_b"])
            counts[row["value_a"]] = row["count_a"]
            counts[row["value_b"]] = row["count_b"]
            union(row["value_a"], row["value_b"])

        clusters = {}
        for value in parent:
            clusters.setdefault(find(value), []).append(value)

        column_mapping = {}
        for members in clusters.values():
            canonical = max(members, key=lambda v: (counts.get(v, 0), v))
            for member in members:
                if member != canonical:
                    column_mapping[member] = canonical
        if column_mapping:
            mappings[column] = column_mapping
    return mappings


@lru_cache(maxsize=1)
def _load_isic_division_to_section() -> dict:
    """Division (int 1-99) -> section letter, read from the official ISIC
    Rev.4 structure file (config.ISIC_REFERENCE_CSV). Rows with a 2-digit
    Code are division rows; their 'Section (1-digit)' column is text like
    'A Agriculture, forestry and fishing' -- the first character is the
    section letter."""
    ref = pd.read_csv(config.ISIC_REFERENCE_CSV, encoding="utf-8-sig")
    ref.columns = [c.strip() for c in ref.columns]
    divisions = ref[ref["Code"].astype(str).str.len() == 2]
    return {
        int(row["Code"]): str(row["Section (1-digit)"]).strip()[0]
        for _, row in divisions.iterrows()
    }


@lru_cache(maxsize=1)
def _load_isic_section_labels() -> dict:
    """Section letter -> full section title, from the same reference file."""
    ref = pd.read_csv(config.ISIC_REFERENCE_CSV, encoding="utf-8-sig")
    ref.columns = [c.strip() for c in ref.columns]
    divisions = ref[ref["Code"].astype(str).str.len() == 2]
    labels = {}
    for section_text in divisions["Section (1-digit)"].astype(str).str.strip().unique():
        letter, _, title = section_text.partition(" ")
        labels[letter] = title
    return labels


@lru_cache(maxsize=1)
def _load_isco_major_group_labels() -> dict:
    """Major group digit ('0'-'9') -> title, read from the official
    ISCO-08 structure file (config.ISCO_REFERENCE_XLSX). Level == 1 rows
    are the 10 major groups."""
    ref = pd.read_excel(config.ISCO_REFERENCE_XLSX, sheet_name=0)
    major_groups = ref[ref["Level"] == 1]
    return {str(row["ISCO 08 Code"]): str(row["Title EN"]) for _, row in major_groups.iterrows()}


def classify_isic_section(isic_series: pd.Series) -> pd.Series:
    """Derive the ISIC Rev.4 section letter (A-U) from a 3-4 digit
    isic_code, using the official structure file. Some divisions < 10
    lose their leading zero in this dataset's export (e.g. '729' for what
    should be '0729') -- codes are zero-padded to 4 digits before the
    division (first 2 digits) is read."""
    division_to_section = _load_isic_division_to_section()

    def _section(code):
        if pd.isna(code):
            return pd.NA
        code_str = str(code).strip().zfill(4)
        if len(code_str) < 2 or not code_str[:2].isdigit():
            return pd.NA
        return division_to_section.get(int(code_str[:2]), pd.NA)

    return isic_series.map(_section)


def classify_isco_major_group(isco_series: pd.Series) -> pd.Series:
    """Derive the ISCO-08 major group (the first digit of the 4-digit
    code) from isco_code, using the official structure file. Same
    leading-zero note as ISIC applies to Major Group 0 (Armed forces) --
    codes shorter than 4 digits are zero-padded first."""
    major_group_labels = _load_isco_major_group_labels()

    def _major_group(code):
        if pd.isna(code):
            return pd.NA
        code_str = str(code).strip()
        if not code_str:
            return pd.NA
        if len(code_str) < 4:
            code_str = code_str.zfill(4)
        first_digit = code_str[0]
        return first_digit if first_digit in major_group_labels else pd.NA

    return isco_series.map(_major_group)


def clean_dataset(name: str, datasets: dict) -> Path:
    """Run the full cleaning stage for one dataset: dedup, the one
    verified auto-correction, every flag-only validation rule, any
    reviewed value mappings, and (ind only) ISIC/ISCO classification.
    Writes the cleaned parquet, a cleaning log, and a flagged-for-review
    CSV. Reads Outputs/typed/<name>_typed.parquet -- run ingest.py first."""
    paths = datasets[name]
    df = pd.read_parquet(paths["typed"])
    log_lines = [f"Cleaning: {name}", f"Rows before: {len(df)}"]

    df, n_dropped = drop_exact_duplicates(df, _ID_COLUMNS[name])
    log_lines.append(f"Exact-duplicate rows dropped (key={_ID_COLUMNS[name]}): {n_dropped}")

    df, n_age_corrected = correct_age_sentinel(df, name)
    log_lines.append(f"Age sentinel (-1) corrected to NaN in {_AGE_COLUMNS[name]}: {n_age_corrected}")

    df, hours_corrected = correct_hours_sentinel(df, name)
    for col, n in hours_corrected.items():
        log_lines.append(f"Hours sentinel (99) corrected to NaN in {col}: {n}")

    flagged = apply_validation_rules(df, name)
    n_flagged_rows = flagged[["hhid", "id2"]].drop_duplicates().shape[0] if len(flagged) else 0
    log_lines.append(
        f"Validation-rule flags: {len(flagged)} flag(s) across {n_flagged_rows} unique row(s), "
        f"{flagged['rule_name'].nunique() if len(flagged) else 0} rule(s) -- see {paths['flagged_for_review'].name}"
    )

    for column, mapping in config.VALUE_MAPPINGS.get(name, {}).items():
        df, n_mapped = apply_value_mapping(df, column, mapping)
        log_lines.append(f"Manual value mapping applied to {column}: {n_mapped} row(s)")
    if not config.VALUE_MAPPINGS.get(name):
        log_lines.append("Manual value mappings: none defined (config.VALUE_MAPPINGS is empty)")

    if paths["near_duplicates"].exists():
        near_duplicates = pd.read_csv(paths["near_duplicates"])
        auto_mapping = build_consolidation_mapping(near_duplicates, min_similarity=0.98)
        for column, mapping in auto_mapping.items():
            df, n_mapped = apply_value_mapping(df, column, mapping)
            log_lines.append(
                f"Auto-consolidated {column}: {len(mapping)} variant(s) merged into their canonical "
                f"value (>=0.98 Jaro-Winkler similarity, majority-vote by frequency), {n_mapped} row(s) affected"
            )
    else:
        log_lines.append("Auto-consolidation skipped: run diagnose.py first to generate near-duplicate candidates")

    if name == "ind":
        df["isic_section"] = classify_isic_section(df["isic_code"])
        df["isic_section_label"] = df["isic_section"].map(_load_isic_section_labels())
        df["isco_major_group"] = classify_isco_major_group(df["isco_code"])
        df["isco_major_group_label"] = df["isco_major_group"].map(_load_isco_major_group_labels())
        log_lines.append(
            f"isic_section derived for {int(df['isic_section'].notna().sum())} of "
            f"{int(df['isic_code'].notna().sum())} rows with an isic_code"
        )
        log_lines.append(
            f"isco_major_group derived for {int(df['isco_major_group'].notna().sum())} of "
            f"{int(df['isco_code'].notna().sum())} rows with an isco_code"
        )

    log_lines.append(f"Rows after: {len(df)}")

    flagged.to_csv(paths["flagged_for_review"], index=False)
    df.to_parquet(paths["cleaned"], index=False)
    df.to_excel(paths["cleaned_xlsx"], index=False, sheet_name=name)
    log_lines.append(f"Cleaned dataset exported to {paths['cleaned_xlsx'].name}")

    paths["cleaning_log"].write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print("\n".join(log_lines))

    return paths["cleaned"]


def clean_all(datasets: dict) -> dict:
    return {name: clean_dataset(name, datasets) for name in datasets}


if __name__ == "__main__":
    clean_all(config.DATASETS)
