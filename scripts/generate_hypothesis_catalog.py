#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from eurusd_quant.research.hypothesis_catalog import (  # noqa: E402
    build_hypothesis_catalog,
    build_hypothesis_priority_summary,
    load_edge_candidates,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the R9 hypothesis catalog from R8 edge candidates.")
    parser.add_argument(
        "--edge-candidates-file",
        type=Path,
        default=Path("outputs/diagnostics/edge_candidates/edge_candidate_definitions.csv"),
        help="Path to the R8 edge candidate definitions CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/diagnostics/hypotheses"),
        help="Directory where the R9 hypothesis artifacts will be written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    edge_candidates = load_edge_candidates(args.edge_candidates_file)
    catalog = build_hypothesis_catalog(edge_candidates)
    priority = build_hypothesis_priority_summary(catalog)

    catalog.to_csv(args.output_dir / "hypothesis_catalog.csv", index=False)
    priority.to_csv(args.output_dir / "hypothesis_priority_summary.csv", index=False)


if __name__ == "__main__":
    main()
