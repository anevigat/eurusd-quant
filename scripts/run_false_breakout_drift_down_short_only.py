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
from eurusd_quant.strategies.false_breakout_reversal import (
    FalseBreakoutReversalConfig,
    FalseBreakoutReversalStrategy,
)


FROZEN_BASE_OVERRIDES = {
    "entry_start_utc": "08:00",
    "entry_end_utc": "09:00",
    "exit_model": "atr_target",
}
CONFIGS = [("drift_down_both", "both"), ("drift_down_short_only", "short_only")]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run false_breakout_reversal on drift_down days for both vs short_only."
    )
    parser.add_argument(
        "--bars-file",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Combined multi-year bars parquet file",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/false_breakout_drift_down_short_only",
        help="Output directory for experiment artifacts",
    )
    parser.add_argument(
        "--down-threshold",
        type=float,
        default=-0.0002,
        help="Drift threshold for drift_down: pre_london_drift < threshold",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def compute_drift_down_days(bars: pd.DataFrame, down_threshold: float) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["trade_date"] = df["timestamp"].dt.date
    tod = df["timestamp"].dt.time

    at_0000 = df.loc[tod == pd.Timestamp("00:00").time(), ["trade_date", "mid_close"]].rename(
        columns={"mid_close": "mid_close_0000"}
    )
    at_0745 = df.loc[tod == pd.Timestamp("07:45").time(), ["trade_date", "mid_close"]].rename(
        columns={"mid_close": "mid_close_0745"}
    )

    daily = at_0000.merge(at_0745, on="trade_date", how="inner")
    daily["pre_london_drift"] = daily["mid_close_0745"] - daily["mid_close_0000"]
    daily["is_drift_down"] = daily["pre_london_drift"] < down_threshold
    return daily


def run_backtest(
    bars: pd.DataFrame,
    execution_cfg: dict[str, Any],
    strategy_cfg: dict[str, Any],
) -> pd.DataFrame:
    strategy = FalseBreakoutReversalStrategy(FalseBreakoutReversalConfig.from_dict(strategy_cfg))
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


def exit_reason_counts(trades: pd.DataFrame) -> dict[str, int]:
    labels = ["stop_loss", "take_profit", "time_exit", "flatten_intraday", "end_of_data"]
    counts = {label: int((trades["exit_reason"] == label).sum()) for label in labels}
    for extra in sorted(set(trades["exit_reason"]) - set(labels)):
        counts[str(extra)] = int((trades["exit_reason"] == extra).sum())
    return counts


def build_metrics(trades: pd.DataFrame) -> dict[str, Any]:
    m = compute_metrics(trades)
    wins = trades.loc[trades["pnl_pips"] > 0, "pnl_pips"] if not trades.empty else pd.Series(dtype=float)
    losses = trades.loc[trades["pnl_pips"] < 0, "pnl_pips"] if not trades.empty else pd.Series(dtype=float)
    return {
        "total_trades": int(m["total_trades"]),
        "win_rate": float(m["win_rate"]),
        "net_pnl": float(m["net_pnl"]),
        "expectancy": float(m["expectancy"]),
        "profit_factor": float(m["profit_factor"]),
        "max_drawdown": float(m["max_drawdown"]),
        "average_win_pips": float(wins.mean()) if not wins.empty else 0.0,
        "average_loss_pips": float(losses.mean()) if not losses.empty else 0.0,
        "exit_reason_counts": exit_reason_counts(trades) if not trades.empty else {},
    }


def build_yearly_rows(configuration: str, trades: pd.DataFrame) -> list[dict[str, Any]]:
    if trades.empty:
        return []
    rows: list[dict[str, Any]] = []
    t = trades.copy()
    t["entry_year"] = pd.to_datetime(t["entry_time"], utc=True).dt.year
    for year, group in t.groupby("entry_year"):
        m = build_metrics(group)
        rows.append(
            {
                "configuration": configuration,
                "year": int(year),
                "total_trades": int(m["total_trades"]),
                "win_rate": float(m["win_rate"]),
                "net_pnl": float(m["net_pnl"]),
                "expectancy": float(m["expectancy"]),
                "profit_factor": float(m["profit_factor"]),
                "max_drawdown": float(m["max_drawdown"]),
                "average_win_pips": float(m["average_win_pips"]),
                "average_loss_pips": float(m["average_loss_pips"]),
            }
        )
    return rows


def print_comparison(summary_rows: list[dict[str, Any]]) -> None:
    table = pd.DataFrame(summary_rows)[
        ["configuration", "total_trades", "win_rate", "profit_factor", "net_pnl", "expectancy"]
    ]
    print("")
    print("Drift-Down Side Comparison")
    print(table.to_string(index=False))


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars_file)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars["trade_date"] = bars["timestamp"].dt.date

    drift_days = compute_drift_down_days(bars, down_threshold=float(args.down_threshold))
    drift_days.to_csv(output_dir / "drift_days.csv", index=False)
    selected_days = set(drift_days.loc[drift_days["is_drift_down"], "trade_date"])

    drift_down_bars = bars[bars["trade_date"].isin(selected_days)].copy()
    drift_down_bars = drift_down_bars.sort_values("timestamp").reset_index(drop=True)
    drift_down_bars = drift_down_bars.drop(columns=["trade_date"])

    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    base_strategy_cfg = dict(strategy_cfg_all["false_breakout_reversal"])

    summary_rows: list[dict[str, Any]] = []
    yearly_rows: list[dict[str, Any]] = []

    for config_name, allowed_side in CONFIGS:
        strategy_cfg = {
            **base_strategy_cfg,
            **FROZEN_BASE_OVERRIDES,
            "allowed_side": allowed_side,
        }
        trades = run_backtest(
            bars=drift_down_bars,
            execution_cfg=execution_cfg,
            strategy_cfg=strategy_cfg,
        )
        metrics = build_metrics(trades)
        summary_rows.append({"configuration": config_name, **metrics})
        yearly_rows.extend(build_yearly_rows(config_name, trades))

        run_dir = output_dir / config_name
        run_dir.mkdir(parents=True, exist_ok=True)
        trades.to_parquet(run_dir / "trades.parquet", index=False)
        with (run_dir / "metrics.json").open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

    yearly_df = pd.DataFrame(yearly_rows).sort_values(["configuration", "year"]).reset_index(drop=True)
    if yearly_df.empty:
        yearly_df = pd.DataFrame(
            columns=[
                "configuration",
                "year",
                "total_trades",
                "win_rate",
                "net_pnl",
                "expectancy",
                "profit_factor",
                "max_drawdown",
                "average_win_pips",
                "average_loss_pips",
            ]
        )
    yearly_df.to_csv(output_dir / "yearly_breakdown.csv", index=False)

    summary = {
        "experiment": "false_breakout_reversal_drift_down_short_only",
        "drift_definition": "pre_london_drift = mid_close(07:45) - mid_close(00:00)",
        "thresholds": {"drift_down_lt": float(args.down_threshold)},
        "frozen_base_configuration": {
            **FROZEN_BASE_OVERRIDES,
            "strategy": "false_breakout_reversal",
        },
        "drift_down_day_count": int(len(selected_days)),
        "configurations": summary_rows,
        "outputs": {
            "summary_json": str(output_dir / "summary.json"),
            "yearly_breakdown_csv": str(output_dir / "yearly_breakdown.csv"),
        },
    }
    with (output_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print_comparison(summary_rows)
    print("")
    print(f"Saved summary: {output_dir / 'summary.json'}")
    print(f"Saved yearly breakdown: {output_dir / 'yearly_breakdown.csv'}")


if __name__ == "__main__":
    main()
