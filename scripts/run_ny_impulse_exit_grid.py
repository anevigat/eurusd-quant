from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

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
from eurusd_quant.utils import normalize_symbol, price_to_pips

DEFAULT_INPUT = "data/bars/15m/eurusd_bars_15m_2018_2024.parquet"
DEFAULT_OUTPUT_ROOT = "outputs/ny_impulse_exit_grid"
DEFAULT_P90_THRESHOLD_PRICE = 0.002455
DEFAULT_ENTRY_RATIO = 0.50


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NY impulse exit-model grid with frozen entry settings.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Bars parquet input")
    parser.add_argument(
        "--output-root",
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory for per-model outputs and summary",
    )
    parser.add_argument(
        "--p90-threshold-price",
        type=float,
        default=DEFAULT_P90_THRESHOLD_PRICE,
        help="Impulse threshold in price units",
    )
    parser.add_argument(
        "--entry-ratio",
        type=float,
        default=DEFAULT_ENTRY_RATIO,
        help="Fixed retracement entry ratio",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_once(bars: pd.DataFrame, strategy_cfg: dict[str, Any], execution_cfg: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    strategy = NYImpulseMeanReversionStrategy(NYImpulseMeanReversionConfig.from_dict(strategy_cfg))
    simulator = ExecutionSimulator(ExecutionConfig.from_dict(execution_cfg))

    for _, bar in bars.iterrows():
        simulator.process_bar(bar)
        if simulator.has_open_position():
            position = simulator.get_open_position()
            if position is not None:
                updated = strategy.update_open_position(bar, position)
                if updated is not None:
                    simulator.update_open_position_brackets(*updated)

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


def summarize(metrics: dict[str, Any], model_name: str, symbol: str) -> dict[str, Any]:
    return {
        "exit_model": model_name,
        "total_trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "net_pnl": float(metrics["net_pnl"]),
        "profit_factor": float(metrics["profit_factor"]),
        "expectancy": float(metrics["expectancy"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "avg_win_pips": float(price_to_pips(symbol, metrics["average_win"])),
        "avg_loss_pips": float(price_to_pips(symbol, metrics["average_loss"])),
    }


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.input)
    if bars.empty:
        raise ValueError("Input bars are empty")

    symbol = normalize_symbol(str(bars.iloc[0].get("symbol", "EURUSD"))) or "EURUSD"
    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")

    if "ny_impulse_mean_reversion" not in strategy_cfg_all:
        raise ValueError("Strategy config 'ny_impulse_mean_reversion' not found")

    base_cfg = dict(strategy_cfg_all["ny_impulse_mean_reversion"])
    threshold_pips = price_to_pips(symbol, float(args.p90_threshold_price))

    models: list[dict[str, Any]] = [
        {
            "name": "retracement_0_50",
            "cfg": {"exit_model": "retracement", "retracement_target_ratio": 0.50},
        },
        {
            "name": "retracement_0_75",
            "cfg": {"exit_model": "retracement", "retracement_target_ratio": 0.75},
        },
        {
            "name": "atr_1_0",
            "cfg": {"exit_model": "atr", "atr_target_multiple": 1.0},
        },
        {
            "name": "atr_1_5",
            "cfg": {"exit_model": "atr", "atr_target_multiple": 1.5},
        },
        {
            "name": "atr_trailing_0_8",
            "cfg": {
                "exit_model": "atr_trailing",
                "initial_stop_atr": 1.0,
                "atr_trail_multiple": 0.8,
            },
        },
        {
            "name": "breakeven_atr_trailing",
            "cfg": {
                "exit_model": "breakeven_atr_trailing",
                "initial_stop_atr": 1.0,
                "breakeven_trigger_atr": 0.5,
                "trailing_start_atr": 1.0,
                "atr_trail_multiple": 0.8,
            },
        },
    ]

    print("exit_model | trades | win_rate | PF | net_pnl | max_dd")
    rows: list[dict[str, Any]] = []

    for model in models:
        cfg = dict(base_cfg)
        cfg["impulse_threshold_pips"] = threshold_pips
        cfg["retracement_entry_ratio"] = float(args.entry_ratio)
        cfg.update(model["cfg"])

        run_dir = output_root / model["name"]
        run_dir.mkdir(parents=True, exist_ok=True)

        trades, metrics = run_once(bars=bars, strategy_cfg=cfg, execution_cfg=execution_cfg)

        trades.to_parquet(run_dir / "trades.parquet", index=False)
        with (run_dir / "metrics.json").open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        row = summarize(metrics=metrics, model_name=model["name"], symbol=symbol)
        rows.append(row)

        print(
            f"{row['exit_model']:>22} | {row['total_trades']:>6} | {row['win_rate']:.4f} | "
            f"{row['profit_factor']:.4f} | {row['net_pnl']:.6f} | {row['max_drawdown']:.6f}"
        )

    summary = {
        "strategy": "ny_impulse_mean_reversion",
        "input": args.input,
        "symbol": symbol,
        "fixed_impulse_threshold_price": float(args.p90_threshold_price),
        "fixed_impulse_threshold_pips": float(threshold_pips),
        "fixed_retracement_entry_ratio": float(args.entry_ratio),
        "results": rows,
    }

    summary_path = output_root / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved summary: {summary_path}")


if __name__ == "__main__":
    main()
