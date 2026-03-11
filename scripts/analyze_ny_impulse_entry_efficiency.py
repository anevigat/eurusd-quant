from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze NY impulse mean-reversion entry timing efficiency"
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Bars parquet path",
    )
    parser.add_argument(
        "--trades",
        default="outputs/ny_impulse_exit_models_extended/atr_1_0/trades.parquet",
        help="Trades parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/ny_impulse_entry_efficiency",
        help="Output directory",
    )
    return parser.parse_args()


def _safe_efficiency(numerator: float, denominator: float) -> float:
    if denominator <= 1e-12:
        raw = 1.0 if abs(numerator) <= 1e-12 else 0.0
    else:
        raw = numerator / denominator
    return float(np.clip(raw, 0.0, 1.0))


def compute_trade_entry_efficiency(trade: pd.Series, bars_slice: pd.DataFrame) -> float:
    side = str(trade["side"])
    entry_price = float(trade["entry_price"])
    exit_price = float(trade["exit_price"])

    if side == "long":
        if "ask_low" not in bars_slice.columns:
            raise KeyError("Bars must contain ask_low for long entry efficiency")
        best_price = float(bars_slice["ask_low"].min())
        numerator = entry_price - best_price
        denominator = abs(exit_price - best_price)
        return _safe_efficiency(numerator, denominator)

    if side == "short":
        if "bid_high" not in bars_slice.columns:
            raise KeyError("Bars must contain bid_high for short entry efficiency")
        best_price = float(bars_slice["bid_high"].max())
        numerator = best_price - entry_price
        denominator = abs(best_price - exit_price)
        return _safe_efficiency(numerator, denominator)

    raise ValueError(f"Unsupported side: {side}")


def summarize_efficiency(series: pd.Series) -> dict[str, float]:
    if series.empty:
        return {
            "mean": 0.0,
            "median": 0.0,
            "p25": 0.0,
            "p75": 0.0,
            "p90": 0.0,
        }
    return {
        "mean": float(series.mean()),
        "median": float(series.median()),
        "p25": float(series.quantile(0.25)),
        "p75": float(series.quantile(0.75)),
        "p90": float(series.quantile(0.90)),
    }


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bars = pd.read_parquet(args.bars)
    trades = pd.read_parquet(args.trades)
    if bars.empty:
        raise ValueError("Bars input is empty")
    if trades.empty:
        raise ValueError("Trades input is empty")

    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)
    trades = trades.sort_values("entry_time").reset_index(drop=True)

    efficiencies: list[float] = []
    best_prices: list[float] = []

    for _, trade in trades.iterrows():
        segment = bars[
            (bars["timestamp"] >= trade["entry_time"]) & (bars["timestamp"] <= trade["exit_time"])
        ]
        if segment.empty:
            raise RuntimeError(
                f"No bars found for trade window {trade['entry_time']} -> {trade['exit_time']}"
            )

        if str(trade["side"]) == "long":
            best_price = float(segment["ask_low"].min())
        else:
            best_price = float(segment["bid_high"].max())

        eff = compute_trade_entry_efficiency(trade, segment)
        efficiencies.append(eff)
        best_prices.append(best_price)

    trades_eff = trades.copy()
    trades_eff["best_entry_price"] = best_prices
    trades_eff["entry_efficiency"] = efficiencies
    trades_eff["trade_outcome"] = np.where(trades_eff["net_pnl"] > 0, "win", "loss")

    all_summary = summarize_efficiency(trades_eff["entry_efficiency"])
    winners = trades_eff[trades_eff["net_pnl"] > 0]
    losers = trades_eff[trades_eff["net_pnl"] <= 0]

    summary = {
        "bars_file": args.bars,
        "trades_file": args.trades,
        "total_trades": int(len(trades_eff)),
        "all_trades": all_summary,
        "winning_trades": {
            "count": int(len(winners)),
            **summarize_efficiency(winners["entry_efficiency"]),
        },
        "losing_trades": {
            "count": int(len(losers)),
            **summarize_efficiency(losers["entry_efficiency"]),
        },
    }

    summary_path = output_dir / "entry_efficiency_summary.json"
    per_trade_path = output_dir / "entry_efficiency_per_trade.csv"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    export_cols = [
        "signal_time",
        "entry_time",
        "exit_time",
        "symbol",
        "side",
        "entry_price",
        "exit_price",
        "best_entry_price",
        "entry_efficiency",
        "net_pnl",
        "trade_outcome",
    ]
    available_cols = [c for c in export_cols if c in trades_eff.columns]
    trades_eff[available_cols].to_csv(per_trade_path, index=False)

    print(f"trades: {summary['total_trades']}")
    print(f"mean_efficiency: {all_summary['mean']:.4f}")
    print(f"median_efficiency: {all_summary['median']:.4f}")
    print(f"p25: {all_summary['p25']:.4f}")
    print(f"p75: {all_summary['p75']:.4f}")
    print(f"p90: {all_summary['p90']:.4f}")
    print(f"\nSaved summary: {summary_path}")
    print(f"Saved per-trade efficiency: {per_trade_path}")


if __name__ == "__main__":
    main()
