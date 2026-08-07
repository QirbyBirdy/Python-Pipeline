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
        "diagnostics_csv": DIAGNOSTICS_DIR / "ind_diagnostics.csv",
        "diagnostics_report": DIAGNOSTICS_DIR / "ind_report.md",
        "problem_inventory": PROBLEM_INVENTORY_DIR / "ind_problem_inventory.md",
        "ingest_log": LOGS_DIR / "ind_ingest.log",
        "dtype_log": LOGS_DIR / "ind_dtype_coercion.log",
    },
    "emig": {
        "csv": DATA_DIR / "glfs-174-emig-public.csv",
        "dictionary": DATA_DIR / "glfs-174-emig-public-dictionary.csv",
        "interim": INTERIM_DIR / "emig_raw.parquet",
        "typed": TYPED_DIR / "emig_typed.parquet",
        "diagnostics_csv": DIAGNOSTICS_DIR / "emig_diagnostics.csv",
        "diagnostics_report": DIAGNOSTICS_DIR / "emig_report.md",
        "problem_inventory": PROBLEM_INVENTORY_DIR / "emig_problem_inventory.md",
        "ingest_log": LOGS_DIR / "emig_ingest.log",
        "dtype_log": LOGS_DIR / "emig_dtype_coercion.log",
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

for _dir in (INTERIM_DIR, TYPED_DIR, DIAGNOSTICS_DIR, PROBLEM_INVENTORY_DIR, LOGS_DIR, CHARTS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
