from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.analytics.metrics import compute_metrics
from eurusd_quant.data.loaders import load_bars
from eurusd_quant.execution.simulator import ExecutionConfig, ExecutionSimulator
from eurusd_quant.strategies.asian_range_compression_breakout import (
    AsianRangeCompressionBreakoutConfig,
    AsianRangeCompressionBreakoutStrategy,
)

DEFAULT_THRESHOLDS = [4.0, 4.5, 4.7]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Asian compression breakout experiments across compression thresholds."
    )
    parser.add_argument(
        "--input",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Bars parquet input",
    )
    parser.add_argument(
        "--output-root",
        default="outputs/asian_compression_breakout_experiments",
        help="Output root directory",
    )
    parser.add_argument(
        "--thresholds",
        type=float,
        nargs="+",
        default=DEFAULT_THRESHOLDS,
        help="Compression ratio thresholds to test",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_backtest_once(
    bars: pd.DataFrame,
    strategy_cfg_dict: dict,
    execution_cfg_dict: dict,
) -> tuple[pd.DataFrame, dict]:
    strategy = AsianRangeCompressionBreakoutStrategy(
        AsianRangeCompressionBreakoutConfig.from_dict(strategy_cfg_dict)
    )
    simulator = ExecutionSimulator(ExecutionConfig.from_dict(execution_cfg_dict))

    for _, bar in bars.iterrows():
        simulator.process_bar(bar)
        order = strategy.generate_order(
            bar,
            has_open_position=simulator.has_open_position(),
            has_pending_order=simulator.has_pending_order(),
        )
        if order is not None:
            simulator.submit_order(order)

    if not bars.empty:
        simulator.close_open_position_at_end(bars.iloc[-1])

    trades = simulator.get_trades_df()
    metrics = compute_metrics(trades)
    return trades, metrics


def summarize(metrics: dict, trades: pd.DataFrame, threshold: float) -> dict:
    avg_duration = float(trades["bars_held"].mean()) if not trades.empty else 0.0
    return {
        "threshold": float(threshold),
        "total_trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "net_pnl": float(metrics["net_pnl"]),
        "profit_factor": float(metrics["profit_factor"]),
        "expectancy": float(metrics["expectancy"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "average_trade_duration": avg_duration,
        "average_win": float(metrics["average_win"]),
        "average_loss": float(metrics["average_loss"]),
    }


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.input)
    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    if "asian_range_compression_breakout" not in strategy_cfg_all:
        raise ValueError("Strategy config 'asian_range_compression_breakout' not found")
    base_strategy_cfg = dict(strategy_cfg_all["asian_range_compression_breakout"])

    all_results: list[dict] = []
    for threshold in args.thresholds:
        run_dir = output_root / f"{threshold:.1f}"
        run_dir.mkdir(parents=True, exist_ok=True)

        strategy_cfg = dict(base_strategy_cfg)
        # Override only compression threshold for this experiment.
        strategy_cfg["compression_atr_ratio"] = float(threshold)

        trades, metrics = run_backtest_once(bars, strategy_cfg, execution_cfg)
        trades.to_parquet(run_dir / "trades.parquet", index=False)
        with (run_dir / "metrics.json").open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        result = summarize(metrics=metrics, trades=trades, threshold=float(threshold))
        all_results.append(result)
        print(
            f"threshold={threshold:.1f} trades={result['total_trades']} "
            f"net_pnl={result['net_pnl']:.6f} pf={result['profit_factor']:.4f}"
        )

    summary = {
        "strategy": "asian_range_compression_breakout",
        "input": args.input,
        "thresholds_tested": [float(t) for t in args.thresholds],
        "results": all_results,
    }
    summary_path = output_root / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
