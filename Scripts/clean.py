"""Stage 3 (build brief Step 6): the actual value-changing cleaning
operations -- exact-duplicate removal, rule-based validation (flag or
correct, per CLEANING_PLAN.md Part 4), value-mapping application, and
ISIC-section / ISCO-major-group classification. Reads the typed parquet
written by ingest.py; writes a cleaned parquet, a cleaning log, and a
flagged-for-review CSV per dataset.

Every correction this module makes is logged with a before/after count.

Course-correction (this file's second pass): a self-audit found the same
underlying mistake in four places -- a check or correction that could
never have caught a real problem even if one existed, because of how it
was scoped or ordered. Each is called out at the point it's fixed below;
the short version:

1. Sentinel correction ran before the consistency check meant to verify
   it, so check_usual_hours_consistency() was validating already-cleaned
   data and could never flag the very rows the sentinel explained. Fixed
   by running it once, deliberately, on the RAW data before any
   correction -- diagnostic only now, not part of the flagged-for-review
   output (see clean_dataset()).
2. check_daily_hours_consistency() compared q3_09 (a CAPI-*computed*
   total) against its own definition (the sum of its components) -- an
   arithmetic identity that's true by construction on genuine data, so
   the check could never fail. Removed; replaced by
   recompute_derived_hours(), which treats q3_09/q3_10/q3_05 as derived
   fields to be recalculated from cleaned components, not raw totals to
   be validated.
3. The -1 "don't know" sentinel verified for age was never generalized --
   it was still live, uncorrected, in q3_07_1..7 and q3_08. Fixed by
   correct_negative_one_hours_sentinel(), the same mechanism as the age
   correction, just applied to the columns where it actually occurs.
4. check_employment_skip_logic() required a literal "No" on all four
   screening questions, but the CAPI skip logic leaves most genuinely
   not-employed respondents blank instead (48% of not-employed rows have
   all four blank) -- blank silently failed the equality check, so those
   rows were never inspected. Fixed by treating blank the same as "No"
   (no evidence of employment), which surfaces 23 rows the old mask
   missed entirely. Tracing those 23 found every one has q2_06 answered
   (an informal sale/handicraft activity that independently routes to job
   coding) -- so q2_06 is now part of the check too, and the complete,
   correct version finds 0 unexplained violations, not 23.
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
# usual_hours_mismatch flags). Every other hours column has ZERO
# occurrences of 99 despite going as high as 168 -- confirms this is
# specific to these two "usual hours" fields, not a general sentinel.
_HOURS_SENTINEL_COLUMNS = {"ind": ["q3_03", "q3_05"], "emig": []}

# Columns where -1 is the same "don't know" sentinel already verified for
# age -- generalized here after a self-audit found it was still live and
# uncorrected in these seven+one columns (see module docstring, item 3).
_NEGATIVE_ONE_HOURS_COLUMNS = {"ind": [f"q3_07_{i}" for i in range(1, 8)] + ["q3_08"], "emig": []}

_FLAGGED_COLUMNS = ["hhid", "id2", "rule_name", "detail"]


def _correct_sentinel(df: pd.DataFrame, columns: list, sentinel) -> tuple:
    """Generic sentinel -> NaN correction, shared by every auto-correction
    in this module (age, hours-99, hours-negative-one) so the mechanism is
    genuinely one implementation, not three copies of the same logic.
    Returns (df, {column: n_corrected})."""
    df = df.copy()
    corrected = {}
    for col in columns:
        mask = df[col] == sentinel
        corrected[col] = int(mask.sum())
        df.loc[mask, col] = pd.NA
    return df, corrected


def _count_changed(before: pd.Series, after: pd.Series) -> int:
    """How many rows actually changed value. Deliberately not just
    `before != after`: with pandas nullable dtypes, comparing a real value
    against NA returns NA (not True), and that silently drops out of a
    sum -- found by this producing "0 changed" on data that had visibly
    changed. Each of the three ways a value can actually change is
    checked explicitly instead."""
    before_na = before.isna()
    after_na = after.isna()
    became_missing = ~before_na & after_na
    became_present = before_na & ~after_na
    both_present_different = ~before_na & ~after_na & (before != after)
    changed = became_missing | became_present | both_present_different
    return int(changed.sum())


def drop_exact_duplicates(df: pd.DataFrame, key_columns: list) -> tuple:
    """Exact-match dedup on key_columns, keeping the first occurrence.
    Returns (deduped_df, n_dropped)."""
    n_before = len(df)
    deduped = df.drop_duplicates(subset=key_columns, keep="first").copy()
    return deduped, n_before - len(deduped)


def correct_age_sentinel(df: pd.DataFrame, name: str) -> tuple:
    """Age == -1 -> NaN. Defensible because diagnose.py's range check
    already confirmed every out-of-range age value is exactly -1 (a
    'don't know' sentinel), not a scattered set of implausible values.
    Returns (df, n_corrected)."""
    df, corrected = _correct_sentinel(df, [_AGE_COLUMNS[name]], -1)
    return df, corrected[_AGE_COLUMNS[name]]


def correct_hours_sentinel(df: pd.DataFrame, name: str) -> tuple:
    """99 -> NaN in q3_03/q3_05 only (see _HOURS_SENTINEL_COLUMNS for the
    evidence). Returns (df, {column: n_corrected})."""
    return _correct_sentinel(df, _HOURS_SENTINEL_COLUMNS[name], 99)


def correct_negative_one_hours_sentinel(df: pd.DataFrame, name: str) -> tuple:
    """-1 -> NaN in the seven daily hours columns and q3_08 (see
    _NEGATIVE_ONE_HOURS_COLUMNS -- the same sentinel already verified for
    age, generalized to where it actually occurs in the hours-worked
    block). Returns (df, {column: n_corrected})."""
    return _correct_sentinel(df, _NEGATIVE_ONE_HOURS_COLUMNS[name], -1)


def recompute_derived_hours(df: pd.DataFrame, name: str) -> tuple:
    """Recompute q3_09 (main-job actual hours), q3_10 (all-jobs actual
    hours), and q3_05 (all-jobs usual hours) directly from their now-
    cleaned components, instead of trusting the raw CAPI-computed/
    self-reported totals or merely flagging a mismatch against them (see
    module docstring, item 2). NaN propagates deliberately: summing a
    week with one unknown day and calling the result a true weekly total
    would understate it, so any missing component makes the derived
    total unknown too. Only recomputes for rows the question actually
    applied to -- doesn't invent a value where one was never asked.
    ind only. Returns (df, {field: n_changed})."""
    if name != "ind":
        return df, {}
    df = df.copy()
    changed = {}

    day_cols = [f"q3_07_{i}" for i in range(1, 8)]
    has_main_job = df["q3_16"].notna()
    q3_09_before = df["q3_09"].astype("Float64")
    q3_09_new = df[day_cols].astype("Float64").sum(axis=1, skipna=False).where(has_main_job)
    changed["q3_09"] = _count_changed(q3_09_before, q3_09_new)
    df["q3_09"] = q3_09_new.astype("Int64")

    # q3_04 (untouched by any sentinel correction) is the reliable "was
    # asked about a second job" indicator -- using q3_08 for this would be
    # circular, since q3_08 is one of the columns just corrected above.
    has_other_job = df["q3_04"].notna()

    q3_10_before = df["q3_10"].astype("Float64")
    q3_10_new = (df["q3_09"].astype("Float64") + df["q3_08"].astype("Float64")).where(has_other_job)
    changed["q3_10"] = _count_changed(q3_10_before, q3_10_new)
    df["q3_10"] = q3_10_new.astype("Int64")

    q3_05_before = df["q3_05"].astype("Float64")
    q3_05_new = (df["q3_03"].astype("Float64") + df["q3_04"].astype("Float64")).where(has_other_job)
    changed["q3_05"] = _count_changed(q3_05_before, q3_05_new)
    df["q3_05"] = q3_05_new.astype("Int64")

    return df, changed


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
    """q3_05 (total usual hours, all jobs) vs q3_03 (main job) + q3_04
    (other jobs), allowing 1 hour of rounding slack. Diagnostic only --
    call this once on the RAW data before any correction (see module
    docstring, item 1); recompute_derived_hours() is what actually fixes
    q3_05 afterward, so this isn't part of the ongoing flagged-for-review
    output."""
    main = df["q3_03"].astype("Float64").fillna(0)
    other = df["q3_04"].astype("Float64").fillna(0)
    total = df["q3_05"].astype("Float64")
    expected = main + other
    diff = (expected - total).abs()
    mask = df["q3_05"].notna() & (diff > 1)
    detail = "q3_03+q3_04=" + expected.astype(str) + " vs q3_05=" + total.astype(str)
    return _build_flags(df, "ind", mask, "usual_hours_mismatch", detail)


def check_employment_skip_logic(df: pd.DataFrame) -> pd.DataFrame:
    """If none of q2_04/q2_05/q2_06/q2_07/q2_10 show any evidence of
    employment, isco_code should be empty.

    Fixed from an earlier version that required a literal 'No' on all
    four gate questions -- but the CAPI skip logic means most genuinely
    not-employed respondents have these fields blank (never asked), not
    explicitly 'No': 48% of not-employed rows (isco_code null) have all
    four blank. Blank silently failed the old equality check, so those
    rows were never inspected at all. Treating blank as 'no evidence',
    same as an explicit 'No', surfaces 23 rows the old version missed.

    Traced all 23 by hand: every one has q2_06 answered (1 or 2 --
    informal cooking-for-sale or handicraft-for-sale activity), which the
    questionnaire routes straight to job coding, correctly skipping
    q2_07/q2_10. q2_06 wasn't in the original check at all. With it
    included, the complete, correct version finds 0 unexplained
    violations, not 23 -- the 23 were real gaps in the *check*, not in
    the data."""
    no_evidence_of_employment = ~(
        (df["q2_04"] == "Yes")
        | (df["q2_05"] == "Yes")
        | (df["q2_06"].notna() & (df["q2_06"] != 99))
        | (df["q2_07"] == "Yes")
        | (df["q2_10"] == "Yes")
    )
    mask = no_evidence_of_employment & df["isco_code"].notna()
    detail = pd.Series(
        "no Yes/positive answer on any employment-screening question (q2_04/05/06/07/10) but isco_code is filled",
        index=df.index,
    )
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


def apply_validation_rules(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Runs every remaining flag-only rule for `name` and concatenates the
    results. Returns flagged_rows -- does not touch df. The two hours-
    consistency checks are deliberately absent here: usual-hours is now a
    one-off diagnostic on raw data (see clean_dataset()), and daily-hours
    was retired outright (module docstring, item 2)."""
    frames = []
    if name == "ind":
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
    """Run the full cleaning stage for one dataset: dedup, every verified
    auto-correction, a pre-correction diagnostic on raw data, every
    flag-only validation rule, recomputation of the derived hours fields,
    any reviewed/auto value mappings, and (ind only) ISIC/ISCO
    classification. Writes the cleaned parquet+xlsx, a cleaning log, and a
    flagged-for-review CSV. Reads Outputs/typed/<name>_typed.parquet --
    run ingest.py first."""
    paths = datasets[name]
    df = pd.read_parquet(paths["typed"])
    log_lines = [f"Cleaning: {name}", f"Rows before: {len(df)}"]

    df, n_dropped = drop_exact_duplicates(df, _ID_COLUMNS[name])
    log_lines.append(f"Exact-duplicate rows dropped (key={_ID_COLUMNS[name]}): {n_dropped}")

    if name == "ind":
        # Diagnostic only, on RAW data, before any correction -- see the
        # module docstring, item 1. This is what "would it have caught one
        # if it existed" actually requires: run the check while it still
        # could fail.
        raw_mismatch = check_usual_hours_consistency(df)
        log_lines.append(
            f"Usual-hours mismatch on RAW data, before any correction: {len(raw_mismatch)} row(s) "
            "(diagnostic only -- recompute_derived_hours() below is what fixes q3_05, not this check)"
        )

    df, n_age_corrected = correct_age_sentinel(df, name)
    log_lines.append(f"Age sentinel (-1) corrected to NaN in {_AGE_COLUMNS[name]}: {n_age_corrected}")

    df, hours_corrected = correct_hours_sentinel(df, name)
    for col, n in hours_corrected.items():
        log_lines.append(f"Hours sentinel (99) corrected to NaN in {col}: {n}")

    df, neg1_corrected = correct_negative_one_hours_sentinel(df, name)
    for col, n in neg1_corrected.items():
        log_lines.append(f"Hours sentinel (-1) corrected to NaN in {col}: {n}")

    df, recompute_changed = recompute_derived_hours(df, name)
    for field, n in recompute_changed.items():
        log_lines.append(f"Recomputed {field} from cleaned components: {n} value(s) changed")

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
