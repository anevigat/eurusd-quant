from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.portfolio.allocator import AllocationConfig
from eurusd_quant.portfolio.exposure import ExposureConfig
from eurusd_quant.portfolio.io import load_portfolio_candidates_config, load_strategy_stream
from eurusd_quant.portfolio.portfolio_backtest import run_portfolio_backtest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run portfolio experiments from candidate strategy artifacts")
    parser.add_argument("--config", default="config/portfolio_candidates.yaml", help="Path to portfolio experiment config")
    parser.add_argument("--experiment", help="Run only a single named experiment")
    parser.add_argument("--output-dir", default="outputs/portfolio_candidates", help="Output root")
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
        allocation_config = AllocationConfig(
            weighting_method=experiment.weighting_method,
            max_weight_per_strategy=experiment.max_weight_per_strategy,
            rebalance_frequency=experiment.rebalance_frequency,
            lookback_days=experiment.lookback_days,
        )
        exposure_config = ExposureConfig(
            max_weight_per_pair=experiment.max_weight_per_pair,
            max_usd_direction_exposure=experiment.max_usd_direction_exposure,
            max_active_strategies_per_pair=experiment.max_active_strategies_per_pair,
            one_strategy_per_pair=experiment.one_strategy_per_pair,
            blocked_strategy_pairs=experiment.blocked_strategy_pairs,
        )
        result = run_portfolio_backtest(streams, allocation_config, exposure_config)

        experiment_dir = output_root / experiment.name
        experiment_dir.mkdir(parents=True, exist_ok=True)
        with (experiment_dir / "metrics.json").open("w", encoding="utf-8") as handle:
            json.dump(result.metrics, handle, indent=2)
        result.equity_curve.to_csv(experiment_dir / "equity_curve.csv", index=False)
        result.weights.to_csv(experiment_dir / "weights.csv", index=False)
        result.contribution_by_strategy.to_csv(experiment_dir / "contribution_by_strategy.csv", index=False)
        result.contribution_by_pair.to_csv(experiment_dir / "contribution_by_pair.csv", index=False)
        result.correlation_matrix.to_csv(experiment_dir / "correlation_matrix.csv", index_label="member_name")
        result.drawdown_contribution.to_csv(experiment_dir / "drawdown_contribution.csv", index=False)
        if not result.scaled_trades.empty:
            result.scaled_trades.to_parquet(experiment_dir / "scaled_trades.parquet", index=False)

        print(f"Saved portfolio results to: {experiment_dir}")


if __name__ == "__main__":
    main()
