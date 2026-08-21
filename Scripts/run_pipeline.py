"""Single-command entry point for the whole pipeline (brief Section 2.2.1:
"There must be one entry point... that executes every stage in the correct
order"). Runs ingest -> diagnose -> clean -> problem_inventory -> impute ->
data_dictionary -> export -> report -> visualize for both datasets, in the
order each stage actually depends on the one before it.

Usage:
    python Scripts/run_pipeline.py
"""

import config
from clean import clean_all
from data_dictionary import write_all as write_data_dictionaries
from diagnose import diagnose_emig, diagnose_ind
from export import export_all
from impute import impute_all
from ingest import ingest_all, type_all
from problem_inventory import build_problem_inventory
from report import build_all as build_reports
from visualize import make_charts


def main() -> None:
    print("=== 1/9 ingest ===")
    ingest_all(config.DATASETS, config.EXPECTED_COUNTS)
    # type_all() writes Outputs/typed/<name>_typed.parquet -- clean.py,
    # impute.py, data_dictionary.py, and report.py all read that file
    # directly (diagnose.py is the one exception; it recomputes typed data
    # itself rather than depending on this cache -- see diagnose.load_typed()).
    type_all(config.DATASETS)

    print("\n=== 2/9 diagnose ===")
    diagnose_ind(config.DATASETS)
    diagnose_emig(config.DATASETS)

    print("\n=== 3/9 clean ===")
    clean_all(config.DATASETS)

    print("\n=== 4/9 problem inventory ===")
    build_problem_inventory(config.DATASETS)

    print("\n=== 5/9 impute ===")
    impute_all(config.DATASETS)

    print("\n=== 6/9 data dictionary ===")
    write_data_dictionaries(config.DATASETS)

    print("\n=== 7/9 export (.sav/.dta/.xlsx/.parquet) ===")
    export_all(config.DATASETS)

    print("\n=== 8/9 automated Word report ===")
    build_reports(config.DATASETS)

    print("\n=== 9/9 charts ===")
    make_charts(config.DATASETS)

    print("\nDone. Outputs/ regenerated end to end.")


if __name__ == "__main__":
    main()
