"""Single-command entry point for the whole pipeline (brief Section 2.2.1:
"There must be one entry point... that executes every stage in the correct
order"). Runs ingest -> diagnose -> clean -> problem_inventory -> visualize
for both datasets, in the order each stage actually depends on the one
before it.

Usage:
    python Scripts/run_pipeline.py
"""

import config
from clean import clean_all
from diagnose import diagnose_emig, diagnose_ind
from ingest import ingest_all
from problem_inventory import build_problem_inventory
from visualize import make_charts


def main() -> None:
    print("=== 1/5 ingest ===")
    ingest_all(config.DATASETS, config.EXPECTED_COUNTS)

    print("\n=== 2/5 diagnose ===")
    diagnose_ind(config.DATASETS)
    diagnose_emig(config.DATASETS)

    print("\n=== 3/5 clean ===")
    clean_all(config.DATASETS)

    print("\n=== 4/5 problem inventory ===")
    build_problem_inventory(config.DATASETS)

    print("\n=== 5/5 charts ===")
    make_charts(config.DATASETS)

    print("\nDone. Outputs/ regenerated end to end.")


if __name__ == "__main__":
    main()
