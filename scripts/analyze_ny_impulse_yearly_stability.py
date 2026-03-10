from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze year-by-year stability for NY impulse mean reversion (best config)."
    )
    parser.add_argument(
        "--trades",
        default="outputs/ny_impulse_entry_experiments/0.50/trades.parquet",
        help="Path to trades parquet",
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Path to bars parquet (tracked in metadata for reproducibility)",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/ny_impulse_yearly_stability",
        help="Output directory",
    )
    return parser.parse_args()


def load_pip_size() -> float:
    with (ROOT / "config" / "execution.yaml").open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return float(cfg["pip_size"])


def profit_factor(pnl: pd.Series) -> float:
    wins = float(pnl[pnl > 0].sum())
    losses_abs = abs(float(pnl[pnl < 0].sum()))
    if losses_abs == 0.0:
        return float(np.inf) if wins > 0 else 0.0
    return float(wins / losses_abs)


def max_drawdown_from_pnl(pnl: pd.Series) -> float:
    if pnl.empty:
        return 0.0
    equity = pnl.cumsum()
    peak = equity.cummax()
    drawdown = equity - peak
    return float(abs(drawdown.min()))


def compute_yearly_stats(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for year, group in trades.groupby("year"):
        pnl = group["net_pnl"]
        wins = group[group["pnl_pips"] > 0]["pnl_pips"]
        losses = group[group["pnl_pips"] < 0]["pnl_pips"]
        rows.append(
            {
                "year": int(year),
                "trades": int(len(group)),
                "win_rate": float((pnl > 0).mean()) if len(group) else 0.0,
                "net_pnl": float(pnl.sum()) if len(group) else 0.0,
                "profit_factor": profit_factor(pnl) if len(group) else 0.0,
                "expectancy": float(pnl.mean()) if len(group) else 0.0,
                "max_drawdown": max_drawdown_from_pnl(pnl),
                "avg_win_pips": float(wins.mean()) if not wins.empty else 0.0,
                "avg_loss_pips": float(losses.mean()) if not losses.empty else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("year").reset_index(drop=True)


def compute_equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    daily = (
        trades.groupby("exit_date", as_index=False)
        .agg(day_pnl=("net_pnl", "sum"))
        .sort_values("exit_date")
        .reset_index(drop=True)
    )
    daily["equity"] = daily["day_pnl"].cumsum()
    return daily[["exit_date", "equity"]].rename(columns={"exit_date": "date"})


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pip_size = load_pip_size()
    trades = pd.read_parquet(args.trades).copy()
    if trades.empty:
        raise ValueError("Trades file is empty")

    for col in ("entry_time", "exit_time"):
        trades[col] = pd.to_datetime(trades[col], utc=True)
    trades = trades.sort_values("exit_time").reset_index(drop=True)
    trades["year"] = trades["entry_time"].dt.year
    trades["exit_date"] = trades["exit_time"].dt.strftime("%Y-%m-%d")
    if "pnl_pips" not in trades.columns:
        trades["pnl_pips"] = trades["net_pnl"] / pip_size

    yearly_stats = compute_yearly_stats(trades)
    equity_curve = compute_equity_curve(trades)

    yearly_path = output_dir / "yearly_stats.csv"
    equity_path = output_dir / "equity_curve.csv"
    yearly_stats.to_csv(yearly_path, index=False)
    equity_curve.to_csv(equity_path, index=False)

    print("year | trades | win_rate | PF | net_pnl | max_dd")
    for _, row in yearly_stats.iterrows():
        print(
            f"{int(row['year'])} | {int(row['trades'])} | {row['win_rate']:.4f} | "
            f"{row['profit_factor']:.4f} | {row['net_pnl']:.6f} | {row['max_drawdown']:.6f}"
        )

    print(f"\nSaved yearly stats: {yearly_path}")
    print(f"Saved equity curve: {equity_path}")


if __name__ == "__main__":
    main()
