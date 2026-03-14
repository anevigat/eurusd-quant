from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.portfolio.correlation import build_correlation_bundle
from eurusd_quant.portfolio.io import load_portfolio_candidates_config, load_strategy_stream


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze redundancy and correlation across strategy artifacts")
    parser.add_argument("--config", default="config/portfolio_candidates.yaml", help="Path to portfolio experiment config")
    parser.add_argument("--experiment", help="Run only a single named experiment")
    parser.add_argument("--output-dir", default="outputs/strategy_correlation", help="Output root")
    parser.add_argument("--rolling-window", type=int, default=20, help="Rolling correlation window in daily observations")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    members, experiments = load_portfolio_candidates_config(args.config)
    selected = [exp for exp in experiments if args.experiment is None or exp.name == args.experiment]
    if not selected:
        raise ValueError(f"No portfolio experiments matched --experiment={args.experiment!r}")

    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    for experiment in selected:
        streams = [load_strategy_stream(members[name]) for name in experiment.member_names]
        bundle = build_correlation_bundle(streams, rolling_window=args.rolling_window)
        experiment_dir = output_root / experiment.name
        experiment_dir.mkdir(parents=True, exist_ok=True)

        daily_pnl = bundle["daily_pnl"]
        if not daily_pnl.empty:
            daily_pnl.to_csv(experiment_dir / "daily_pnl.csv", index_label="date")
        bundle["correlation_matrix"].to_csv(experiment_dir / "correlation_matrix.csv", index_label="member_name")
        bundle["rolling_correlation"].to_csv(experiment_dir / "rolling_correlation.csv", index=False)
        bundle["overlap_summary"].to_csv(experiment_dir / "overlap_summary.csv", index=False)
        with (experiment_dir / "summary.json").open("w", encoding="utf-8") as handle:
            json.dump(bundle["diversification_summary"], handle, indent=2)

        print(f"Saved correlation analysis to: {experiment_dir}")


if __name__ == "__main__":
    main()
