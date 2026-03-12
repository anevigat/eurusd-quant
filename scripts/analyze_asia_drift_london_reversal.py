from __future__ import annotations

import argparse
import json
import sys
from datetime import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.data.loaders import load_bars


ASIA_START = time(0, 0)
ASIA_END = time(7, 0)
LONDON_START = time(7, 0)
LONDON_END = time(10, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze Asian drift vs London reversal behavior on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/asia_drift_london_reversal_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    return parser.parse_args()


def _window_mask(series: pd.Series, start: time, end: time) -> pd.Series:
    if start <= end:
        return (series >= start) & (series < end)
    return (series >= start) | (series < end)


def compute_daily_metrics(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time

    rows: list[dict[str, object]] = []
    for date, day in df.groupby("date", sort=True):
        asia = day.loc[_window_mask(day["tod"], ASIA_START, ASIA_END)]
        london = day.loc[_window_mask(day["tod"], LONDON_START, LONDON_END)]

        if asia.empty or london.empty:
            continue

        asia_open = float(asia.iloc[0]["mid_open"])
        asia_close = float(asia.iloc[-1]["mid_close"])
        drift = asia_close - asia_open
        drift_magnitude = abs(drift)

        london_high = float(london["mid_high"].max())
        london_low = float(london["mid_low"].min())

        if drift > 0:
            drift_direction = "up"
            reversal_magnitude = max(0.0, asia_close - london_low)
            follow_through = max(0.0, london_high - asia_close)
            adverse_move = reversal_magnitude
        elif drift < 0:
            drift_direction = "down"
            reversal_magnitude = max(0.0, london_high - asia_close)
            follow_through = max(0.0, asia_close - london_low)
            adverse_move = reversal_magnitude
        else:
            drift_direction = "flat"
            reversal_magnitude = 0.0
            follow_through = max(london_high - asia_close, asia_close - london_low, 0.0)
            adverse_move = follow_through

        if drift_magnitude > 0:
            reversal_ratio = reversal_magnitude / drift_magnitude
            follow_through_ratio = follow_through / drift_magnitude
            adverse_move_ratio = adverse_move / drift_magnitude
        else:
            reversal_ratio = float("nan")
            follow_through_ratio = float("nan")
            adverse_move_ratio = float("nan")

        rows.append(
            {
                "date": date,
                "asia_open": asia_open,
                "asia_close": asia_close,
                "drift": drift,
                "drift_magnitude": drift_magnitude,
                "drift_direction": drift_direction,
                "london_high": london_high,
                "london_low": london_low,
                "reversal_magnitude": reversal_magnitude,
                "follow_through": follow_through,
                "adverse_move": adverse_move,
                "reversal_ratio": reversal_ratio,
                "follow_through_ratio": follow_through_ratio,
                "adverse_move_ratio": adverse_move_ratio,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("No daily rows were produced from the input bars")
    return out.sort_values("date").reset_index(drop=True)


def _q(series: pd.Series, q: float) -> float:
    clean = series.dropna()
    if clean.empty:
        return 0.0
    return float(clean.quantile(q))


def build_distribution(daily: pd.DataFrame) -> pd.DataFrame:
    stats = []
    metrics = {
        "drift_magnitude": daily["drift_magnitude"],
        "reversal_ratio": daily["reversal_ratio"],
        "follow_through_ratio": daily["follow_through_ratio"],
        "adverse_move_ratio": daily["adverse_move_ratio"],
    }
    for metric, series in metrics.items():
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            stats.append({"metric": metric, "stat": label, "value": _q(series, q)})
    return pd.DataFrame(stats)


def build_summary(daily: pd.DataFrame, dataset_path: str) -> dict[str, object]:
    days = len(daily)
    up = daily[daily["drift_direction"] == "up"]
    down = daily[daily["drift_direction"] == "down"]
    non_flat = daily[daily["drift_direction"].isin(["up", "down"])]

    reversal_ratio = non_flat["reversal_ratio"].dropna()
    follow_ratio = non_flat["follow_through_ratio"].dropna()
    adverse_ratio = non_flat["adverse_move_ratio"].dropna()

    reversal_dominates = (non_flat["reversal_ratio"] > non_flat["follow_through_ratio"]).dropna()

    return {
        "dataset": dataset_path,
        "windows_utc": {
            "asia": {"start": ASIA_START.strftime("%H:%M"), "end_exclusive": ASIA_END.strftime("%H:%M")},
            "london": {"start": LONDON_START.strftime("%H:%M"), "end_exclusive": LONDON_END.strftime("%H:%M")},
        },
        "days_analyzed": int(days),
        "up_drift_frequency": float(len(up) / days) if days else 0.0,
        "down_drift_frequency": float(len(down) / days) if days else 0.0,
        "flat_drift_frequency": float((days - len(up) - len(down)) / days) if days else 0.0,
        "median_drift_magnitude": _q(daily["drift_magnitude"], 0.50),
        "median_reversal_ratio": _q(reversal_ratio, 0.50),
        "p75_reversal_ratio": _q(reversal_ratio, 0.75),
        "p90_reversal_ratio": _q(reversal_ratio, 0.90),
        "median_follow_through_ratio": _q(follow_ratio, 0.50),
        "median_adverse_move_ratio": _q(adverse_ratio, 0.50),
        "reversal_dominates_frequency": float(reversal_dominates.mean()) if not reversal_dominates.empty else 0.0,
    }


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars)
    daily = compute_daily_metrics(bars)
    distribution = build_distribution(daily)
    summary = build_summary(daily, dataset_path=args.bars)

    daily_path = output_dir / "daily_metrics.csv"
    distribution_path = output_dir / "distribution.csv"
    summary_path = output_dir / "summary.json"

    daily.to_csv(daily_path, index=False)
    distribution.to_csv(distribution_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"up_drift_frequency: {summary['up_drift_frequency']:.4f}")
    print(f"down_drift_frequency: {summary['down_drift_frequency']:.4f}")
    print(f"median_reversal_ratio: {summary['median_reversal_ratio']:.4f}")
    print(f"median_follow_through_ratio: {summary['median_follow_through_ratio']:.4f}")
    print(f"median_adverse_move_ratio: {summary['median_adverse_move_ratio']:.4f}")
    print(f"reversal_dominates_frequency: {summary['reversal_dominates_frequency']:.4f}")

    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {distribution_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
