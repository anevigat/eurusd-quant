from __future__ import annotations

import argparse
import csv
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

DEFAULT_INPUT = "data/bars/15m/eurusd_bars_15m_2018_2024.parquet"
DEFAULT_OUTPUT_ROOT = "outputs/ny_impulse_walkforward"
DEFAULT_P90_THRESHOLD_PRICE = 0.002455

# Rolling walk-forward windows requested by research spec.
WALKFORWARD_WINDOWS = [
    (2018, 2020, 2021),
    (2019, 2021, 2022),
    (2020, 2022, 2023),
    (2021, 2023, 2024),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NY impulse walk-forward validation.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Bars parquet input")
    parser.add_argument(
        "--output-root",
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory for walk-forward outputs",
    )
    parser.add_argument(
        "--p90-price-threshold",
        type=float,
        default=DEFAULT_P90_THRESHOLD_PRICE,
        help="P90 impulse threshold in price units",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_backtest(
    bars: pd.DataFrame,
    strategy_cfg: dict[str, Any],
    execution_cfg: dict[str, Any],
) -> pd.DataFrame:
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

    return simulator.get_trades_df()


def build_summary_row(
    train_start: int,
    train_end: int,
    test_year: int,
    trades: pd.DataFrame,
    pip_size: float,
) -> dict[str, float | int]:
    metrics = compute_metrics(trades)
    wins = trades.loc[trades["pnl_pips"] > 0, "pnl_pips"] if not trades.empty else pd.Series(dtype=float)
    losses = trades.loc[trades["pnl_pips"] < 0, "pnl_pips"] if not trades.empty else pd.Series(dtype=float)

    return {
        "train_start": train_start,
        "train_end": train_end,
        "test_year": test_year,
        "trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "profit_factor": float(metrics["profit_factor"]),
        "net_pnl": float(metrics["net_pnl"]),
        "expectancy": float(metrics["expectancy"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "avg_win_pips": float(wins.mean()) if not wins.empty else 0.0,
        "avg_loss_pips": float(losses.mean()) if not losses.empty else 0.0,
        "_pip_size": pip_size,
    }


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.input)
    if bars.empty:
        raise ValueError("Bars dataset is empty")

    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategies_cfg = load_yaml(ROOT / "config" / "strategies.yaml")
    if "ny_impulse_mean_reversion" not in strategies_cfg:
        raise ValueError("Strategy config 'ny_impulse_mean_reversion' not found")

    pip_size = float(execution_cfg["pip_size"])
    threshold_pips = float(args.p90_price_threshold) / pip_size

    # Frozen deployment configuration (entry logic unchanged).
    frozen_cfg = dict(strategies_cfg["ny_impulse_mean_reversion"])
    frozen_cfg["impulse_threshold_pips"] = threshold_pips
    frozen_cfg["retracement_entry_ratio"] = 0.50
    frozen_cfg["exit_model"] = "atr"
    frozen_cfg["atr_target_multiple"] = 1.0

    bars = bars.copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars["year"] = bars["timestamp"].dt.year

    summary_rows: list[dict[str, float | int]] = []
    equity_parts: list[pd.DataFrame] = []

    print("test_year | trades | win_rate | PF | net_pnl | max_dd")
    for train_start, train_end, test_year in WALKFORWARD_WINDOWS:
        year_bars = bars.loc[bars["year"] == test_year].copy()
        if year_bars.empty:
            raise ValueError(f"No bars found for test year {test_year}")

        trades = run_backtest(year_bars, strategy_cfg=frozen_cfg, execution_cfg=execution_cfg)
        row = build_summary_row(train_start, train_end, test_year, trades, pip_size)
        summary_rows.append(row)

        print(
            f"{test_year} | {int(row['trades'])} | {row['win_rate']:.4f} | "
            f"{row['profit_factor']:.4f} | {row['net_pnl']:.6f} | {row['max_drawdown']:.6f}"
        )

        if not trades.empty:
            t = trades.copy()
            t["exit_time"] = pd.to_datetime(t["exit_time"], utc=True)
            t["date"] = t["exit_time"].dt.strftime("%Y-%m-%d")
            daily = (
                t.groupby("date", as_index=False)
                .agg(day_pnl=("net_pnl", "sum"))
                .sort_values("date")
            )
            daily["test_year"] = test_year
            equity_parts.append(daily)

    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.drop(columns=["_pip_size"])
    summary_df = summary_df[
        [
            "train_start",
            "train_end",
            "test_year",
            "trades",
            "win_rate",
            "profit_factor",
            "net_pnl",
            "expectancy",
            "max_drawdown",
            "avg_win_pips",
            "avg_loss_pips",
        ]
    ]

    summary_path = output_root / "walkforward_summary.csv"
    summary_df.to_csv(summary_path, index=False, quoting=csv.QUOTE_MINIMAL)

    if equity_parts:
        equity_df = pd.concat(equity_parts, ignore_index=True)
        equity_df = equity_df.sort_values(["date", "test_year"]).reset_index(drop=True)
        equity_df["equity"] = equity_df["day_pnl"].cumsum()
        equity_df = equity_df[["date", "equity", "test_year"]]
    else:
        equity_df = pd.DataFrame(columns=["date", "equity", "test_year"])

    equity_path = output_root / "equity_curve.csv"
    equity_df.to_csv(equity_path, index=False, quoting=csv.QUOTE_MINIMAL)

    metadata = {
        "strategy": "ny_impulse_mean_reversion",
        "dataset": args.input,
        "walkforward_windows": [
            {"train_start": s, "train_end": e, "test_year": t} for s, e, t in WALKFORWARD_WINDOWS
        ],
        "frozen_configuration": {
            "impulse_threshold_price": float(args.p90_price_threshold),
            "impulse_threshold_pips": float(threshold_pips),
            "retracement_entry_ratio": 0.50,
            "exit_model": "atr",
            "atr_target_multiple": 1.0,
        },
        "summary_file": str(summary_path),
        "equity_curve_file": str(equity_path),
    }
    with (output_root / "run_metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nSaved summary: {summary_path}")
    print(f"Saved equity curve: {equity_path}")


if __name__ == "__main__":
    main()
