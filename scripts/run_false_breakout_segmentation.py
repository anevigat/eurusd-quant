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
from eurusd_quant.strategies.false_breakout_reversal import (
    FalseBreakoutReversalConfig,
    FalseBreakoutReversalStrategy,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run false breakout segmentation experiments")
    parser.add_argument(
        "--input",
        default="data/bars/15m/eurusd_bars_15m_2023.parquet",
        help="Bars parquet input",
    )
    parser.add_argument(
        "--output-root",
        default="outputs/false_breakout_reversal_segmentation",
        help="Directory to store per-run outputs and summary",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def exit_reason_counts(trades: pd.DataFrame) -> dict[str, int]:
    labels = ["stop_loss", "take_profit", "time_exit", "flatten_intraday", "end_of_data"]
    counts = {label: int((trades["exit_reason"] == label).sum()) for label in labels}
    for label in sorted(set(trades["exit_reason"]) - set(labels)):
        counts[str(label)] = int((trades["exit_reason"] == label).sum())
    return counts


def run_combo(
    bars: pd.DataFrame,
    execution_cfg: dict,
    base_strategy_cfg: dict,
    side: str,
    entry_start: str,
    entry_end: str,
) -> tuple[pd.DataFrame, dict]:
    cfg_data = dict(base_strategy_cfg)
    cfg_data["allowed_side"] = side
    cfg_data["entry_start_utc"] = entry_start
    cfg_data["entry_end_utc"] = entry_end
    strategy = FalseBreakoutReversalStrategy(FalseBreakoutReversalConfig.from_dict(cfg_data))
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


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    if "false_breakout_reversal" not in strategy_cfg_all:
        raise ValueError("false_breakout_reversal strategy config not found")
    base_strategy_cfg = strategy_cfg_all["false_breakout_reversal"]

    bars = load_bars(args.input)

    sides = ["both", "long_only", "short_only"]
    windows = [("07:00", "08:00"), ("08:00", "09:00"), ("09:00", "10:00")]

    rows: list[dict] = []

    for side in sides:
        for start, end in windows:
            tag = f"{side}_{start.replace(':', '')}_{end.replace(':', '')}"
            run_dir = output_root / tag
            run_dir.mkdir(parents=True, exist_ok=True)

            trades, metrics = run_combo(
                bars=bars,
                execution_cfg=execution_cfg,
                base_strategy_cfg=base_strategy_cfg,
                side=side,
                entry_start=start,
                entry_end=end,
            )
            trades.to_parquet(run_dir / "trades.parquet", index=False)
            with (run_dir / "metrics.json").open("w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2)

            wins = trades.loc[trades["pnl_pips"] > 0, "pnl_pips"] if not trades.empty else pd.Series(dtype=float)
            losses = (
                trades.loc[trades["pnl_pips"] < 0, "pnl_pips"] if not trades.empty else pd.Series(dtype=float)
            )

            rows.append(
                {
                    "combination": tag,
                    "side": side,
                    "entry_window": f"{start}-{end}",
                    "total_trades": int(metrics["total_trades"]),
                    "win_rate": float(metrics["win_rate"]),
                    "net_pnl": float(metrics["net_pnl"]),
                    "expectancy": float(metrics["expectancy"]),
                    "profit_factor": float(metrics["profit_factor"]),
                    "max_drawdown": float(metrics["max_drawdown"]),
                    "average_win_pips": float(wins.mean()) if not wins.empty else 0.0,
                    "average_loss_pips": float(losses.mean()) if not losses.empty else 0.0,
                    "exit_reason_counts": exit_reason_counts(trades) if not trades.empty else {},
                    "output_dir": str(run_dir),
                }
            )

    summary_rows = sorted(rows, key=lambda r: r["net_pnl"], reverse=True)
    summary_df = pd.DataFrame(summary_rows)
    best = summary_rows[0]
    worst = summary_rows[-1]

    comparison_df = summary_df[
        [
            "combination",
            "side",
            "entry_window",
            "total_trades",
            "win_rate",
            "net_pnl",
            "expectancy",
            "profit_factor",
            "max_drawdown",
        ]
    ]

    by_side = (
        summary_df.sort_values("net_pnl", ascending=False)
        .groupby("side", as_index=False)
        .first()[
            [
                "side",
                "combination",
                "entry_window",
                "total_trades",
                "win_rate",
                "net_pnl",
                "profit_factor",
            ]
        ]
        .rename(columns={"combination": "best_combination"})
    )
    by_window = (
        summary_df[summary_df["side"] == "both"]
        .sort_values("entry_window")[
            [
                "entry_window",
                "total_trades",
                "win_rate",
                "net_pnl",
                "profit_factor",
            ]
        ]
        .to_dict(orient="records")
    )
    print("False Breakout Segmentation Results")
    print(comparison_df.to_string(index=False))
    print("")
    print("Best by side")
    print(by_side.to_string(index=False))
    print("")
    print(
        "Best combination: "
        f"{best['combination']} (net_pnl={best['net_pnl']}, profit_factor={best['profit_factor']})"
    )
    print(
        "Worst combination: "
        f"{worst['combination']} (net_pnl={worst['net_pnl']}, profit_factor={worst['profit_factor']})"
    )

    summary = {
        "input": args.input,
        "combinations": summary_rows,
        "by_side_best": by_side.to_dict(orient="records"),
        "by_window_for_both_side": by_window,
        "best_combination": best,
        "worst_combination": worst,
    }
    with (output_root / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved summary: {output_root / 'summary.json'}")


if __name__ == "__main__":
    main()
