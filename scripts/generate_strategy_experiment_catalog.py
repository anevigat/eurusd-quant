#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from eurusd_quant.research.strategy_experiment_catalog import (  # noqa: E402
    build_experiment_catalog,
    build_validation_ladder,
    load_hypothesis_catalog,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the R10 strategy experiment catalog and validation ladder.")
    parser.add_argument(
        "--hypothesis-catalog-file",
        type=Path,
        default=Path("outputs/diagnostics/hypotheses/hypothesis_catalog.csv"),
        help="Path to the R9 hypothesis catalog CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/diagnostics/strategy_experiments"),
        help="Directory where the R10 experiment-planning artifacts will be written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    hypotheses = load_hypothesis_catalog(args.hypothesis_catalog_file)
    experiment_catalog = build_experiment_catalog(hypotheses)
    validation_ladder = build_validation_ladder()

    experiment_catalog.to_csv(args.output_dir / "experiment_catalog.csv", index=False)
    validation_ladder.to_csv(args.output_dir / "validation_ladder.csv", index=False)


if __name__ == "__main__":
    main()
