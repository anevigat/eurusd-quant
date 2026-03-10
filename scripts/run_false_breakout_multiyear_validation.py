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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run frozen false-breakout-reversal validation on yearly bars."
    )
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--bars-dir", default="data/bars/15m")
    parser.add_argument(
        "--output-root",
        default="outputs/experiments/false_breakout_reversal_atr_target_0809",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_year_metrics(trades: pd.DataFrame) -> dict[str, float]:
    core = compute_metrics(trades)
    wins = trades.loc[trades["pnl_pips"] > 0, "pnl_pips"] if not trades.empty else pd.Series(dtype=float)
    losses = trades.loc[trades["pnl_pips"] < 0, "pnl_pips"] if not trades.empty else pd.Series(dtype=float)
    return {
        "trade_count": int(core["total_trades"]),
        "win_rate": float(core["win_rate"]),
        "profit_factor": float(core["profit_factor"]),
        "net_pnl": float(core["net_pnl"]),
        "expectancy": float(core["expectancy"]),
        "max_drawdown": float(core["max_drawdown"]),
        "average_win_pips": float(wins.mean()) if not wins.empty else 0.0,
        "average_loss_pips": float(losses.mean()) if not losses.empty else 0.0,
    }


def run_year(
    bars_path: Path,
    output_dir: Path,
    execution_cfg: dict[str, Any],
    strategy_cfg: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, float]]:
    bars = load_bars(str(bars_path))
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

    trades = simulator.get_trades_df()
    metrics = compute_metrics(trades)

    output_dir.mkdir(parents=True, exist_ok=True)
    trades.to_parquet(output_dir / "trades.parquet", index=False)
    with (output_dir / "metrics.json").open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    return trades, build_year_metrics(trades)


def build_monthly_rows(trades: pd.DataFrame, year: int) -> list[dict[str, Any]]:
    if trades.empty:
        return []
    month_key = pd.to_datetime(trades["entry_time"], utc=True).dt.strftime("%Y-%m")
    grouped = (
        trades.assign(month=month_key)
        .groupby("month", as_index=False)
        .agg(
            trade_count=("net_pnl", "size"),
            net_pnl=("net_pnl", "sum"),
            pnl_pips=("pnl_pips", "sum"),
        )
    )
    rows: list[dict[str, Any]] = []
    for record in grouped.to_dict(orient="records"):
        rows.append(
            {
                "year": year,
                "month": record["month"],
                "trade_count": int(record["trade_count"]),
                "net_pnl": float(record["net_pnl"]),
                "pnl_pips": float(record["pnl_pips"]),
            }
        )
    return rows


def main() -> None:
    args = parse_args()
    if args.end_year < args.start_year:
        raise ValueError("--end-year must be >= --start-year")

    years = list(range(args.start_year, args.end_year + 1))
    bars_dir = Path(args.bars_dir)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    if "false_breakout_reversal" not in strategy_cfg_all:
        raise ValueError("false_breakout_reversal strategy config not found")

    base_strategy_cfg = dict(strategy_cfg_all["false_breakout_reversal"])
    frozen_strategy_cfg = {**base_strategy_cfg, **FROZEN_CONFIG_OVERRIDES}

    summary_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []

    for year in years:
        bars_path = bars_dir / f"eurusd_bars_15m_{year}.parquet"
        if not bars_path.exists():
            raise FileNotFoundError(f"Missing bars file for {year}: {bars_path}")

        year_output = output_root / str(year)
        trades, year_metrics = run_year(
            bars_path=bars_path,
            output_dir=year_output,
            execution_cfg=execution_cfg,
            strategy_cfg=frozen_strategy_cfg,
        )
        summary_rows.append({"year": year, **year_metrics})
        monthly_rows.extend(build_monthly_rows(trades, year))
        print(
            f"{year}: trades={year_metrics['trade_count']} "
            f"win_rate={year_metrics['win_rate']:.4f} "
            f"net_pnl={year_metrics['net_pnl']:.6f} "
            f"profit_factor={year_metrics['profit_factor']:.4f}"
        )

    summary_df = pd.DataFrame(summary_rows).sort_values("year").reset_index(drop=True)
    summary_path = output_root / "summary.csv"
    summary_df.to_csv(summary_path, index=False)

    monthly_df = pd.DataFrame(monthly_rows).sort_values(["year", "month"]).reset_index(drop=True)
    monthly_path = output_root / "monthly_pnl.csv"
    if monthly_df.empty:
        monthly_df = pd.DataFrame(columns=["year", "month", "trade_count", "net_pnl", "pnl_pips"])
    monthly_df.to_csv(monthly_path, index=False)

    metadata = {
        "strategy": "false_breakout_reversal",
        "frozen_configuration": frozen_strategy_cfg,
        "years": years,
        "output_root": str(output_root),
        "summary_file": str(summary_path),
        "monthly_file": str(monthly_path),
    }
    with (output_root / "run_metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("")
    print(f"Saved summary: {summary_path}")
    print(f"Saved monthly pnl: {monthly_path}")
    print(f"Saved metadata: {output_root / 'run_metadata.json'}")


if __name__ == "__main__":
    main()
