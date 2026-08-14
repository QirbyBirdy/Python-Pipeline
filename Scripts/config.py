"""Path configuration for the GLFS pipeline. All paths used by the pipeline
scripts (ingest, diagnostics, problem_inventory) are defined here."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "Data"
OUTPUTS_DIR = PROJECT_ROOT / "Outputs"

INTERIM_DIR = OUTPUTS_DIR / "interim"
TYPED_DIR = OUTPUTS_DIR / "typed"
DIAGNOSTICS_DIR = OUTPUTS_DIR / "diagnostics"
PROBLEM_INVENTORY_DIR = OUTPUTS_DIR / "problem_inventory"
LOGS_DIR = OUTPUTS_DIR / "logs"
CHARTS_DIR = OUTPUTS_DIR / "charts"

DATASETS = {
    "ind": {
        "csv": DATA_DIR / "glfs-174-ind-public.csv",
        "dictionary": DATA_DIR / "glfs-174-ind-public-dictionary.csv",
        "interim": INTERIM_DIR / "ind_raw.parquet",
        "typed": TYPED_DIR / "ind_typed.parquet",
        "cleaned": TYPED_DIR / "ind_cleaned.parquet",
        "diagnostics_csv": DIAGNOSTICS_DIR / "ind_diagnostics.csv",
        "diagnostics_report": DIAGNOSTICS_DIR / "ind_report.md",
        "problem_inventory": PROBLEM_INVENTORY_DIR / "ind_problem_inventory.md",
        "ingest_log": LOGS_DIR / "ind_ingest.log",
        "dtype_log": LOGS_DIR / "ind_dtype_coercion.log",
        "cleaning_log": LOGS_DIR / "ind_cleaning.log",
        "flagged_for_review": LOGS_DIR / "ind_flagged_for_review.csv",
        "near_duplicates": LOGS_DIR / "ind_near_duplicates.csv",
        "casing_check": LOGS_DIR / "ind_casing_consistency.csv",
    },
    "emig": {
        "csv": DATA_DIR / "glfs-174-emig-public.csv",
        "dictionary": DATA_DIR / "glfs-174-emig-public-dictionary.csv",
        "interim": INTERIM_DIR / "emig_raw.parquet",
        "typed": TYPED_DIR / "emig_typed.parquet",
        "cleaned": TYPED_DIR / "emig_cleaned.parquet",
        "diagnostics_csv": DIAGNOSTICS_DIR / "emig_diagnostics.csv",
        "diagnostics_report": DIAGNOSTICS_DIR / "emig_report.md",
        "problem_inventory": PROBLEM_INVENTORY_DIR / "emig_problem_inventory.md",
        "ingest_log": LOGS_DIR / "emig_ingest.log",
        "dtype_log": LOGS_DIR / "emig_dtype_coercion.log",
        "cleaning_log": LOGS_DIR / "emig_cleaning.log",
        "flagged_for_review": LOGS_DIR / "emig_flagged_for_review.csv",
        "near_duplicates": LOGS_DIR / "emig_near_duplicates.csv",
        "casing_check": LOGS_DIR / "emig_casing_consistency.csv",
    },
}

# Expected row counts from the source documentation (Data/glfs-q4-2017-methodological-report.pdf,
# "Introduction", p.3): the Q4 2017 GLFS "visited a probability sample of 3,783 households and
# 13,853 individuals". The report does not state a headline household/individual count for the
# emigration module specifically, so "emig" has no documented expectation to check against --
# ingest.py logs its observed counts for the record but does not compare them to anything.
EXPECTED_COUNTS = {
    "ind": {"households": 3783, "individuals": 13853},
}

# Bounded, verified single-parent skip-gate relationships, transcribed from
# the "Ask only if X" instructions in the questionnaire (methodological
# report, Annex 3) -- NOT exhaustive coverage of every column's skip logic
# (see CLEANING_PLAN.md, Part 2). {dataset: [(dependent_col, gate_col,
# applies_when_gate_equals), ...]}
SKIP_PATTERNS = {
    "ind": [
        ("q2_02", "q2_01", "Yes"),
        ("q2_03", "q2_01", "Yes"),
        ("q1_12", "q1_11", "Yes"),
        ("q1_13", "q1_11", "Yes"),
        ("q3_04", "q3_01", "Yes"),
        ("q3_05", "q3_01", "Yes"),
        ("q2_15", "q2_14", "Yes"),
    ],
    "emig": [],
}
# q1_14/q1_15/q1_16 were originally included here too (gated by q1_11), but
# classify_missingness() showed 12-43% "incidental" missingness for them --
# too high to be just measurement noise. They actually branch further off
# q1_13's specific value (education level attended), not just whether
# q1_11 == "Yes" -- a nested gate this bounded single-parent model doesn't
# capture. Removed rather than reported under a misleading label; this is
# exactly the kind of finding CLEANING_PLAN.md's own "Verify" step for
# Part 2 was written to catch.

# Free-text columns (no coded companion) -- candidates for the near-duplicate
# value finder (CLEANING_PLAN.md, Part 3) and the eventual manual value
# mapping (Part 5). From ingest.py's recommend_dtypes() "free-text" flags.
FREE_TEXT_COLUMNS = {
    "ind": ["q2_02", "q3_15b", "q3_30", "q3_31", "q3_32", "q3_33"],
    "emig": ["q7_08", "q7_15"],
}

# Monetary/income columns to IQR-outlier-check (CLEANING_PLAN.md, Part 4a).
# Flag only -- never silently dropped or altered.
MONETARY_COLUMNS = {
    "ind": [
        "q6_01", "q6_04a", "q6_04b", "q6_04c", "q6_04d", "q6_04e", "q6_04f",
        "q6_05a", "q6_05b", "q6_05c", "q6_05d", "q6_05e", "q6_05f", "q6_05g", "q6_05h", "q6_05i",
        "q6_06", "q6_07", "q6_09", "q6_10", "q6_11", "q6_12", "q6_13",
        "q6_14", "q6_15", "q6_16", "q6_17", "q6_18", "q6_19",
        "q6_20a", "q6_20b", "q6_21", "q6_22", "q6_24a", "q6_24b",
    ],
    "emig": [],
}

# Manual value-consolidation mappings for free-text columns, populated only
# after a human reviews find_near_duplicate_values()'s candidate output
# (CLEANING_PLAN.md, Part 5). Starts empty by design.
VALUE_MAPPINGS = {
    "ind": {},
    "emig": {},
}

# Official reference tables for ISIC-section / ISCO-major-group
# classification (clean.py). Not survey-specific -- these are the real
# ISIC Rev.4 and ISCO-08 structure files, so the classification logic
# reads its lookup tables from these rather than a hand-transcribed copy
# (hand-transcribed values were built first and cross-checked as correct
# against these files, but the files are now the source of truth).
ISIC_REFERENCE_CSV = DATA_DIR / "isic-rev4-structure.csv"
ISCO_REFERENCE_XLSX = DATA_DIR / "isco-08-structure.xlsx"

for _dir in (INTERIM_DIR, TYPED_DIR, DIAGNOSTICS_DIR, PROBLEM_INVENTORY_DIR, LOGS_DIR, CHARTS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
