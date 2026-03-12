from __future__ import annotations

import argparse
import json
import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.data.loaders import load_bars


LONDON_START = time(7, 0)
LONDON_END = time(12, 0)
NY_START = time(12, 0)
NY_END = time(16, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze London impulse to NY reversal behavior on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/london_impulse_ny_reversal_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    parser.add_argument(
        "--strong-impulse-atr-multiple",
        type=float,
        default=1.0,
        help="Strong impulse threshold as impulse_size >= multiple * ATR",
    )
    return parser.parse_args()


def _window_mask(series: pd.Series, start: time, end: time) -> pd.Series:
    if start <= end:
        return (series >= start) & (series < end)
    return (series >= start) | (series < end)


def _safe_q(series: pd.Series, q: float) -> float:
    clean = series.dropna()
    if clean.empty:
        return 0.0
    return float(clean.quantile(q))


def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["mid_close"].shift(1)
    tr = pd.concat(
        [
            df["mid_high"] - df["mid_low"],
            (df["mid_high"] - prev_close).abs(),
            (df["mid_low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def compute_daily_metrics(bars: pd.DataFrame, strong_impulse_atr_multiple: float) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["atr"] = _compute_atr(df, period=14)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time

    rows: list[dict[str, object]] = []

    for date, day in df.groupby("date", sort=True):
        london = day.loc[_window_mask(day["tod"], LONDON_START, LONDON_END)]
        ny = day.loc[_window_mask(day["tod"], NY_START, NY_END)]
        if london.empty or ny.empty:
            continue

        london_open = float(london.iloc[0]["mid_open"])
        london_close = float(london.iloc[-1]["mid_close"])
        impulse_size = abs(london_close - london_open)

        atr_ref = float(london.iloc[-1]["atr"]) if pd.notna(london.iloc[-1]["atr"]) else np.nan
        if np.isnan(atr_ref) or atr_ref <= 0 or impulse_size <= 0:
            continue

        impulse_direction = "bullish" if london_close > london_open else "bearish"
        impulse_to_atr_ratio = impulse_size / atr_ref
        strong_impulse_flag = impulse_size >= (strong_impulse_atr_multiple * atr_ref)

        if impulse_direction == "bullish":
            reversal = max(0.0, london_close - float(ny["mid_low"].min()))
            adverse = max(0.0, float(ny["mid_high"].max()) - london_close)
        else:
            reversal = max(0.0, float(ny["mid_high"].max()) - london_close)
            adverse = max(0.0, london_close - float(ny["mid_low"].min()))

        rows.append(
            {
                "date": date,
                "london_open": london_open,
                "london_close": london_close,
                "impulse_direction": impulse_direction,
                "impulse_size": impulse_size,
                "atr_ref": atr_ref,
                "impulse_to_atr_ratio": impulse_to_atr_ratio,
                "strong_london_impulse_flag": bool(strong_impulse_flag),
                "reversal_size": reversal,
                "adverse_move_size": adverse,
                "reversal_ratio": reversal / impulse_size,
                "adverse_move_ratio": adverse / impulse_size,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("No daily rows produced from dataset")
    return out


def build_distribution(daily: pd.DataFrame) -> pd.DataFrame:
    strong = daily[daily["strong_london_impulse_flag"]].copy()
    rows: list[dict[str, object]] = []
    for metric in ["impulse_to_atr_ratio", "reversal_ratio", "adverse_move_ratio"]:
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _safe_q(strong[metric], q)})
    return pd.DataFrame(rows)


def build_summary(
    daily: pd.DataFrame,
    dataset_path: str,
    strong_impulse_atr_multiple: float,
) -> dict[str, object]:
    strong = daily[daily["strong_london_impulse_flag"]].copy()
    bull = strong[strong["impulse_direction"] == "bullish"]
    bear = strong[strong["impulse_direction"] == "bearish"]

    return {
        "dataset": dataset_path,
        "london_window_utc": {"start": LONDON_START.strftime("%H:%M"), "end_exclusive": LONDON_END.strftime("%H:%M")},
        "ny_window_utc": {"start": NY_START.strftime("%H:%M"), "end_exclusive": NY_END.strftime("%H:%M")},
        "strong_impulse_atr_multiple": strong_impulse_atr_multiple,
        "days_analyzed": int(len(daily)),
        "strong_london_impulse_frequency": float(len(strong) / len(daily)) if len(daily) else 0.0,
        "bullish_impulse_frequency": float(len(bull) / len(strong)) if len(strong) else 0.0,
        "bearish_impulse_frequency": float(len(bear) / len(strong)) if len(strong) else 0.0,
        "median_reversal_ratio": _safe_q(strong["reversal_ratio"], 0.50),
        "p75_reversal_ratio": _safe_q(strong["reversal_ratio"], 0.75),
        "p90_reversal_ratio": _safe_q(strong["reversal_ratio"], 0.90),
        "median_adverse_move_ratio": _safe_q(strong["adverse_move_ratio"], 0.50),
    }


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars)
    daily = compute_daily_metrics(bars, strong_impulse_atr_multiple=args.strong_impulse_atr_multiple)
    distribution = build_distribution(daily)
    summary = build_summary(
        daily,
        dataset_path=args.bars,
        strong_impulse_atr_multiple=args.strong_impulse_atr_multiple,
    )

    daily_path = out_dir / "daily_metrics.csv"
    dist_path = out_dir / "distribution.csv"
    summary_path = out_dir / "summary.json"

    daily.to_csv(daily_path, index=False)
    distribution.to_csv(dist_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"strong_london_impulse_frequency: {summary['strong_london_impulse_frequency']:.4f}")
    print(f"median_reversal_ratio: {summary['median_reversal_ratio']:.4f}")
    print(f"median_adverse_move_ratio: {summary['median_adverse_move_ratio']:.4f}")
    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
