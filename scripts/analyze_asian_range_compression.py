from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze Asian range compression ratio distribution (asian_range / ATR)."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Path to EURUSD M15 bars parquet",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/asian_range_compression_distribution",
        help="Directory for summary.json and daily_ratios.csv",
    )
    parser.add_argument("--atr-period", type=int, default=14, help="ATR rolling window")
    return parser.parse_args()


def compute_atr(bars: pd.DataFrame, period: int) -> pd.Series:
    prev_close = bars["mid_close"].shift(1)
    high_low = bars["mid_high"] - bars["mid_low"]
    high_prev = (bars["mid_high"] - prev_close).abs()
    low_prev = (bars["mid_low"] - prev_close).abs()
    tr = np.maximum.reduce([high_low.to_numpy(), high_prev.to_numpy(), low_prev.to_numpy()])
    tr_series = pd.Series(tr, index=bars.index)
    return tr_series.rolling(window=period, min_periods=period).mean()


def build_daily_ratios(bars: pd.DataFrame, atr_period: int) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["time"] = df["timestamp"].dt.time
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["atr"] = compute_atr(df, period=atr_period)

    asian_mask = (df["time"] >= pd.Timestamp("00:00").time()) & (df["time"] < pd.Timestamp("06:00").time())
    asian = df.loc[asian_mask].copy()
    if asian.empty:
        raise ValueError("No Asian-session rows found for [00:00, 06:00)")

    asian_ranges = (
        asian.groupby("date")
        .agg(asian_high=("mid_high", "max"), asian_low=("mid_low", "min"))
        .reset_index()
    )
    asian_ranges["asian_range"] = asian_ranges["asian_high"] - asian_ranges["asian_low"]

    asian_last_atr = asian.groupby("date").tail(1)[["date", "atr"]].copy()
    daily = asian_ranges.merge(asian_last_atr, on="date", how="inner")
    daily = daily[daily["atr"].notna() & (daily["atr"] > 0.0)].copy()
    daily["compression_ratio"] = daily["asian_range"] / daily["atr"]
    return daily[["date", "asian_range", "atr", "compression_ratio"]].sort_values("date")


def summarize_distribution(ratios: pd.Series) -> dict[str, float]:
    return {
        "min": float(ratios.min()),
        "p5": float(ratios.quantile(0.05)),
        "p10": float(ratios.quantile(0.10)),
        "p20": float(ratios.quantile(0.20)),
        "p25": float(ratios.quantile(0.25)),
        "p50": float(ratios.quantile(0.50)),
        "p75": float(ratios.quantile(0.75)),
        "p90": float(ratios.quantile(0.90)),
        "p95": float(ratios.quantile(0.95)),
        "max": float(ratios.max()),
    }


def print_summary_table(summary: dict[str, float]) -> None:
    order = ["min", "p5", "p10", "p20", "p25", "p50", "p75", "p90", "p95", "max"]
    print("quantile | compression_ratio")
    for key in order:
        print(f"{key:>7} | {summary[key]:.6f}")


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bars = pd.read_parquet(args.bars, columns=["timestamp", "mid_high", "mid_low", "mid_close"])
    daily = build_daily_ratios(bars=bars, atr_period=args.atr_period)
    if daily.empty:
        raise ValueError("Daily compression dataset is empty after ATR warm-up filtering")

    summary = summarize_distribution(daily["compression_ratio"])
    summary_payload = {
        "bars_file": args.bars,
        "atr_period": args.atr_period,
        "days_analyzed": int(len(daily)),
        **summary,
    }

    daily_path = out_dir / "daily_ratios.csv"
    summary_path = out_dir / "summary.json"
    daily.to_csv(daily_path, index=False)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    print_summary_table(summary)
    print(f"\nSaved daily ratios to: {daily_path}")
    print(f"Saved summary to: {summary_path}")


if __name__ == "__main__":
    main()
