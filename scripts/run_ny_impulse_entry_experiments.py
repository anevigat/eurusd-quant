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
from eurusd_quant.strategies.ny_impulse_mean_reversion import (
    NYImpulseMeanReversionConfig,
    NYImpulseMeanReversionStrategy,
)


DEFAULT_ENTRY_RATIOS = [0.30, 0.40, 0.50]
DEFAULT_P90_PRICE_THRESHOLD = 0.002455


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NY impulse entry trigger experiments.")
    parser.add_argument(
        "--input",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Bars parquet input",
    )
    parser.add_argument(
        "--output-root",
        default="outputs/ny_impulse_entry_experiments",
        help="Directory for per-ratio outputs and summary",
    )
    parser.add_argument(
        "--entry-ratios",
        type=float,
        nargs="+",
        default=DEFAULT_ENTRY_RATIOS,
        help="Retracement entry ratios to test",
    )
    parser.add_argument(
        "--p90-price-threshold",
        type=float,
        default=DEFAULT_P90_PRICE_THRESHOLD,
        help="Fixed p90 impulse threshold in price units",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_once(bars: pd.DataFrame, strategy_cfg: dict, execution_cfg: dict) -> tuple[pd.DataFrame, dict]:
    strategy = NYImpulseMeanReversionStrategy(NYImpulseMeanReversionConfig.from_dict(strategy_cfg))
    simulator = ExecutionSimulator(ExecutionConfig.from_dict(execution_cfg))

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


def summarize(ratio: float, metrics: dict, pip_size: float) -> dict:
    return {
        "entry_ratio": float(ratio),
        "total_trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "net_pnl": float(metrics["net_pnl"]),
        "profit_factor": float(metrics["profit_factor"]),
        "expectancy": float(metrics["expectancy"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "avg_win_pips": float(metrics["average_win"] / pip_size) if pip_size > 0 else 0.0,
        "avg_loss_pips": float(metrics["average_loss"] / pip_size) if pip_size > 0 else 0.0,
    }


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.input)
    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    if "ny_impulse_mean_reversion" not in strategy_cfg_all:
        raise ValueError("Strategy config 'ny_impulse_mean_reversion' not found")
    base_strategy_cfg = dict(strategy_cfg_all["ny_impulse_mean_reversion"])

    pip_size = float(execution_cfg["pip_size"])
    threshold_pips = float(args.p90_price_threshold) / pip_size

    results: list[dict] = []
    print("entry_ratio | trades | win_rate | PF | net_pnl | max_dd")
    for ratio in args.entry_ratios:
        run_dir = output_root / f"{ratio:.2f}"
        run_dir.mkdir(parents=True, exist_ok=True)

        strategy_cfg = dict(base_strategy_cfg)
        strategy_cfg["impulse_threshold_pips"] = threshold_pips
        # Override only entry trigger level for this experiment.
        strategy_cfg["retracement_entry_ratio"] = float(ratio)

        trades, metrics = run_once(bars, strategy_cfg, execution_cfg)
        trades.to_parquet(run_dir / "trades.parquet", index=False)
        with (run_dir / "metrics.json").open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        row = summarize(ratio=ratio, metrics=metrics, pip_size=pip_size)
        results.append(row)
        print(
            f"{ratio:>10.2f} | {row['total_trades']:>6} | {row['win_rate']:.4f} | "
            f"{row['profit_factor']:.4f} | {row['net_pnl']:.6f} | {row['max_drawdown']:.6f}"
        )

    summary = {
        "strategy": "ny_impulse_mean_reversion",
        "input": args.input,
        "fixed_impulse_threshold_price": float(args.p90_price_threshold),
        "fixed_impulse_threshold_pips": float(threshold_pips),
        "results": results,
    }
    summary_path = output_root / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved summary: {summary_path}")


if __name__ == "__main__":
    main()
