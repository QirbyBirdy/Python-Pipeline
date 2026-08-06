"""CLI entrypoint: run ingest -> diagnostics -> problem_inventory for one or
both GLFS datasets.

Usage:
    python Scripts/run_pipeline.py [--dataset ind|emig|both]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from glfs_pipeline.diagnostics import diagnose
from glfs_pipeline.ingest import ingest
from glfs_pipeline.problem_inventory import draft


def run(dataset: str) -> None:
    names = list(config.DATASETS) if dataset == "both" else [dataset]
    for name in names:
        print(f"[{name}] ingesting...")
        ingest(name, config.DATASETS)
        print(f"[{name}] running diagnostics...")
        diagnose(name, config.DATASETS)
        print(f"[{name}] drafting problem inventory...")
        draft(name, config.DATASETS)
        print(f"[{name}] done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the GLFS ingestion/diagnostics pipeline."
    )
    parser.add_argument("--dataset", choices=["ind", "emig", "both"], default="both")
    args = parser.parse_args()
    run(args.dataset)


if __name__ == "__main__":
    main()
