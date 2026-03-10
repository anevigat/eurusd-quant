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


DEFAULT_THRESHOLDS_PRICE = {
    "p50": 0.001265,
    "p75": 0.001755,
    "p90": 0.002455,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NY impulse threshold experiments.")
    parser.add_argument(
        "--input",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Bars parquet input",
    )
    parser.add_argument(
        "--output-root",
        default="outputs/ny_impulse_threshold_experiments",
        help="Directory for per-threshold outputs and summary",
    )
    parser.add_argument(
        "--p50-price-threshold",
        type=float,
        default=DEFAULT_THRESHOLDS_PRICE["p50"],
        help="p50 impulse threshold in price units",
    )
    parser.add_argument(
        "--p75-price-threshold",
        type=float,
        default=DEFAULT_THRESHOLDS_PRICE["p75"],
        help="p75 impulse threshold in price units",
    )
    parser.add_argument(
        "--p90-price-threshold",
        type=float,
        default=DEFAULT_THRESHOLDS_PRICE["p90"],
        help="p90 impulse threshold in price units",
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


def summarize_result(label: str, threshold_pips: float, threshold_price: float, metrics: dict, pip_size: float) -> dict:
    return {
        "threshold": label,
        "threshold_pips": float(threshold_pips),
        "threshold_price": float(threshold_price),
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

    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    if "ny_impulse_mean_reversion" not in strategy_cfg_all:
        raise ValueError("Strategy config 'ny_impulse_mean_reversion' not found")

    bars = load_bars(args.input)
    base_strategy_cfg = dict(strategy_cfg_all["ny_impulse_mean_reversion"])
    pip_size = float(execution_cfg["pip_size"])

    thresholds_price = {
        "p50": float(args.p50_price_threshold),
        "p75": float(args.p75_price_threshold),
        "p90": float(args.p90_price_threshold),
    }

    results: list[dict] = []
    print("threshold | trades | win_rate | PF | net_pnl | max_dd")
    for label, threshold_price in thresholds_price.items():
        threshold_pips = threshold_price / pip_size
        strategy_cfg = dict(base_strategy_cfg)
        # Override only the impulse threshold.
        strategy_cfg["impulse_threshold_pips"] = threshold_pips

        run_dir = output_root / label
        run_dir.mkdir(parents=True, exist_ok=True)

        trades, metrics = run_once(bars=bars, strategy_cfg=strategy_cfg, execution_cfg=execution_cfg)
        trades.to_parquet(run_dir / "trades.parquet", index=False)
        with (run_dir / "metrics.json").open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        row = summarize_result(
            label=label,
            threshold_pips=threshold_pips,
            threshold_price=threshold_price,
            metrics=metrics,
            pip_size=pip_size,
        )
        results.append(row)
        print(
            f"{label:>8} | {row['total_trades']:>6} | {row['win_rate']:.4f} | "
            f"{row['profit_factor']:.4f} | {row['net_pnl']:.6f} | {row['max_drawdown']:.6f}"
        )

    summary = {
        "strategy": "ny_impulse_mean_reversion",
        "input": args.input,
        "results": results,
    }
    summary_path = output_root / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved summary: {summary_path}")


if __name__ == "__main__":
    main()
