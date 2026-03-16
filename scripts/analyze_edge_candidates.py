#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from eurusd_quant.research.edge_candidate_detection import (
    build_candidate_outcome_profiles,
    build_candidate_region_subregions,
    build_pair_breakdown,
    build_regime_breakdown,
    build_time_of_day_breakdown,
    generate_edge_candidate_definitions,
    load_base_candidate_region,
    select_inventory_columns,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze edge candidates inside the expanded contextual breach region.")
    parser.add_argument(
        "--diagnostics-root",
        type=Path,
        default=Path("outputs/diagnostics"),
        help="Root directory containing the upstream R4-R7 diagnostics outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/diagnostics/edge_candidates"),
        help="Directory to write the edge-candidate artifacts into.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    base_region = load_base_candidate_region(args.diagnostics_root)
    candidate_inventory = select_inventory_columns(base_region)
    subregions = build_candidate_region_subregions(base_region)
    pair_breakdown = build_pair_breakdown(base_region)
    time_breakdown = build_time_of_day_breakdown(base_region)
    regime_breakdown = build_regime_breakdown(base_region)
    definitions = generate_edge_candidate_definitions(base_region)
    outcome_profiles = build_candidate_outcome_profiles(base_region, definitions)

    candidate_inventory.to_csv(args.output_dir / "candidate_region_inventory.csv", index=False)
    subregions.to_csv(args.output_dir / "candidate_region_subregions.csv", index=False)
    outcome_profiles.to_csv(args.output_dir / "candidate_outcome_profiles.csv", index=False)
    pair_breakdown.to_csv(args.output_dir / "candidate_pair_breakdown.csv", index=False)
    time_breakdown.to_csv(args.output_dir / "candidate_time_of_day_breakdown.csv", index=False)
    regime_breakdown.to_csv(args.output_dir / "candidate_regime_breakdown.csv", index=False)
    definitions.to_csv(args.output_dir / "edge_candidate_definitions.csv", index=False)

    notes = {
        "base_region_definition": "Expanded contextual breaches, evaluated on aligned +4-bar outcomes from the R7 candidate pattern.",
        "primary_contexts": ["London", "early New York", "London -> New York boundary"],
        "pooled_min_candidate_sample": 400,
        "pair_min_candidate_sample": 200,
        "definition_count": int(len(definitions)),
    }
    (args.output_dir / "edge_candidate_notes.json").write_text(json.dumps(notes, indent=2) + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
