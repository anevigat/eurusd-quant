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


FROZEN_CONFIG_OVERRIDES = {
    "allowed_side": "both",
    "entry_start_utc": "08:00",
    "entry_end_utc": "09:00",
    "exit_model": "atr_target",
}
REGIME_ORDER = ["drift_down", "drift_flat", "drift_up"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run false_breakout_reversal frozen config by pre-London drift regime."
    )
    parser.add_argument(
        "--bars-file",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Combined multi-year bars parquet file",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/false_breakout_pre_london_drift",
        help="Output directory for regime experiment artifacts",
    )
    parser.add_argument(
        "--down-threshold",
        type=float,
        default=-0.0002,
        help="Drift threshold below which day is drift_down",
    )
    parser.add_argument(
        "--up-threshold",
        type=float,
        default=0.0002,
        help="Drift threshold above which day is drift_up",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_regime(drift: float, down_threshold: float, up_threshold: float) -> str:
    if drift < down_threshold:
        return "drift_down"
    if drift > up_threshold:
        return "drift_up"
    return "drift_flat"


def compute_daily_drift_regimes(
    bars: pd.DataFrame, down_threshold: float, up_threshold: float
) -> pd.DataFrame:
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
    daily["regime"] = daily["pre_london_drift"].apply(
        lambda x: classify_regime(float(x), down_threshold, up_threshold)
    )
    return daily


def run_backtest_for_bars(
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


def build_regime_metrics(trades: pd.DataFrame) -> dict[str, Any]:
    metrics = compute_metrics(trades)
    wins = trades.loc[trades["pnl_pips"] > 0, "pnl_pips"] if not trades.empty else pd.Series(dtype=float)
    losses = trades.loc[trades["pnl_pips"] < 0, "pnl_pips"] if not trades.empty else pd.Series(dtype=float)

    return {
        "total_trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "net_pnl": float(metrics["net_pnl"]),
        "expectancy": float(metrics["expectancy"]),
        "profit_factor": float(metrics["profit_factor"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "average_win_pips": float(wins.mean()) if not wins.empty else 0.0,
        "average_loss_pips": float(losses.mean()) if not losses.empty else 0.0,
        "exit_reason_counts": exit_reason_counts(trades) if not trades.empty else {},
    }


def build_yearly_rows(regime: str, trades: pd.DataFrame) -> list[dict[str, Any]]:
    if trades.empty:
        return []
    rows: list[dict[str, Any]] = []
    by_year = trades.copy()
    by_year["entry_year"] = pd.to_datetime(by_year["entry_time"], utc=True).dt.year
    for year, group in by_year.groupby("entry_year"):
        m = build_regime_metrics(group)
        rows.append(
            {
                "regime": regime,
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


def print_comparison_table(summary_rows: list[dict[str, Any]]) -> None:
    table = pd.DataFrame(summary_rows)[
        ["regime", "total_trades", "win_rate", "profit_factor", "net_pnl", "expectancy"]
    ]
    table = table.set_index("regime").reindex(REGIME_ORDER).reset_index()
    print("")
    print("Pre-London Drift Regime Comparison")
    print(table.to_string(index=False))

    non_empty = [row for row in summary_rows if row["total_trades"] > 0]
    if non_empty:
        best = max(non_empty, key=lambda r: r["net_pnl"])
        worst = min(non_empty, key=lambda r: r["net_pnl"])
        print("")
        print(
            f"Best regime by net_pnl: {best['regime']} "
            f"(net_pnl={best['net_pnl']:.6f}, profit_factor={best['profit_factor']:.4f})"
        )
        print(
            f"Worst regime by net_pnl: {worst['regime']} "
            f"(net_pnl={worst['net_pnl']:.6f}, profit_factor={worst['profit_factor']:.4f})"
        )


def main() -> None:
    args = parse_args()
    if args.down_threshold > args.up_threshold:
        raise ValueError("--down-threshold must be <= --up-threshold")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars_file)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars["trade_date"] = bars["timestamp"].dt.date

    regime_days = compute_daily_drift_regimes(
        bars=bars,
        down_threshold=float(args.down_threshold),
        up_threshold=float(args.up_threshold),
    )
    regime_days.to_csv(output_dir / "regime_days.csv", index=False)

    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    base_strategy_cfg = dict(strategy_cfg_all["false_breakout_reversal"])
    frozen_strategy_cfg = {**base_strategy_cfg, **FROZEN_CONFIG_OVERRIDES}

    summary_rows: list[dict[str, Any]] = []
    yearly_rows: list[dict[str, Any]] = []

    for regime in REGIME_ORDER:
        days = set(regime_days.loc[regime_days["regime"] == regime, "trade_date"])
        regime_bars = bars[bars["trade_date"].isin(days)].copy()
        regime_bars = regime_bars.sort_values("timestamp").reset_index(drop=True)
        regime_bars = regime_bars.drop(columns=["trade_date"])

        trades = run_backtest_for_bars(
            bars=regime_bars,
            execution_cfg=execution_cfg,
            strategy_cfg=frozen_strategy_cfg,
        )
        metrics = build_regime_metrics(trades)
        summary_rows.append(
            {
                "regime": regime,
                "day_count": int(len(days)),
                **metrics,
            }
        )
        yearly_rows.extend(build_yearly_rows(regime, trades))

        regime_dir = output_dir / regime
        regime_dir.mkdir(parents=True, exist_ok=True)
        trades.to_parquet(regime_dir / "trades.parquet", index=False)
        with (regime_dir / "metrics.json").open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

    regime_yearly = pd.DataFrame(yearly_rows).sort_values(["regime", "year"]).reset_index(drop=True)
    if regime_yearly.empty:
        regime_yearly = pd.DataFrame(
            columns=[
                "regime",
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
    regime_yearly.to_csv(output_dir / "regime_yearly.csv", index=False)

    summary = {
        "experiment": "false_breakout_reversal_pre_london_drift",
        "frozen_configuration": frozen_strategy_cfg,
        "drift_definition": "pre_london_drift = mid_close(07:45) - mid_close(00:00)",
        "thresholds": {
            "drift_down_lt": float(args.down_threshold),
            "drift_flat_between": [float(args.down_threshold), float(args.up_threshold)],
            "drift_up_gt": float(args.up_threshold),
        },
        "regime_day_counts": {
            regime: int((regime_days["regime"] == regime).sum()) for regime in REGIME_ORDER
        },
        "regimes": summary_rows,
        "outputs": {
            "summary_json": str(output_dir / "summary.json"),
            "regime_yearly_csv": str(output_dir / "regime_yearly.csv"),
        },
    }
    with (output_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print_comparison_table(summary_rows)
    print("")
    print(f"Saved summary: {output_dir / 'summary.json'}")
    print(f"Saved yearly breakdown: {output_dir / 'regime_yearly.csv'}")


if __name__ == "__main__":
    main()
