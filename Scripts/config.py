"""Path configuration for the GLFS pipeline. All paths used by the pipeline
scripts (ingest, diagnostics, problem_inventory) are defined here."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "Data"
OUTPUTS_DIR = PROJECT_ROOT / "Outputs"

INTERIM_DIR = OUTPUTS_DIR / "interim"
DIAGNOSTICS_DIR = OUTPUTS_DIR / "diagnostics"
PROBLEM_INVENTORY_DIR = OUTPUTS_DIR / "problem_inventory"

DATASETS = {
    "ind": {
        "csv": DATA_DIR / "glfs-174-ind-public.csv",
        "dictionary": DATA_DIR / "glfs-174-ind-public-dictionary.csv",
        "interim": INTERIM_DIR / "ind_raw.parquet",
        "diagnostics_csv": DIAGNOSTICS_DIR / "ind_diagnostics.csv",
        "diagnostics_report": DIAGNOSTICS_DIR / "ind_report.md",
        "problem_inventory": PROBLEM_INVENTORY_DIR / "ind_problem_inventory.md",
    },
    "emig": {
        "csv": DATA_DIR / "glfs-174-emig-public.csv",
        "dictionary": DATA_DIR / "glfs-174-emig-public-dictionary.csv",
        "interim": INTERIM_DIR / "emig_raw.parquet",
        "diagnostics_csv": DIAGNOSTICS_DIR / "emig_diagnostics.csv",
        "diagnostics_report": DIAGNOSTICS_DIR / "emig_report.md",
        "problem_inventory": PROBLEM_INVENTORY_DIR / "emig_problem_inventory.md",
    },
}

for _dir in (INTERIM_DIR, DIAGNOSTICS_DIR, PROBLEM_INVENTORY_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
