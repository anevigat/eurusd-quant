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


ASIAN_START = time(0, 0)
ASIAN_END = time(7, 0)
LONDON_START = time(7, 0)
LONDON_END = time(10, 0)
NY_START = time(13, 0)
NY_END = time(16, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze midpoint reversion behavior for Asian and previous-day ranges."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/range_midpoint_reversion_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
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


def _touches_midpoint(window: pd.DataFrame, midpoint: float) -> bool:
    if window.empty or pd.isna(midpoint):
        return False
    return bool(((window["mid_low"] <= midpoint) & (window["mid_high"] >= midpoint)).any())


def _daily_high_low(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("date", as_index=False)
        .agg(prev_day_high=("mid_high", "max"), prev_day_low=("mid_low", "min"))
        .sort_values("date")
        .reset_index(drop=True)
    )


def compute_daily_metrics(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time

    daily_hl = _daily_high_low(df)
    daily_hl["prev_day_midpoint"] = (daily_hl["prev_day_high"] + daily_hl["prev_day_low"]) / 2.0
    daily_hl["date_next"] = daily_hl["date"].shift(-1)

    prev_mid_by_date = {
        row["date_next"]: row["prev_day_midpoint"]
        for _, row in daily_hl.dropna(subset=["date_next", "prev_day_midpoint"]).iterrows()
    }

    rows: list[dict[str, object]] = []
    for date, day in df.groupby("date", sort=True):
        asian = day.loc[_window_mask(day["tod"], ASIAN_START, ASIAN_END)]
        london = day.loc[_window_mask(day["tod"], LONDON_START, LONDON_END)]
        ny = day.loc[_window_mask(day["tod"], NY_START, NY_END)]

        if asian.empty or london.empty or ny.empty:
            continue

        asian_high = float(asian["mid_high"].max())
        asian_low = float(asian["mid_low"].min())
        asian_mid = (asian_high + asian_low) / 2.0
        prev_mid = float(prev_mid_by_date.get(date, float("nan")))

        london_open = float(london.iloc[0]["mid_open"])
        ny_open = float(ny.iloc[0]["mid_open"])

        rows.append(
            {
                "date": date,
                "asian_midpoint": asian_mid,
                "prev_day_midpoint": prev_mid,
                "asian_midpoint_hit_london": _touches_midpoint(london, asian_mid),
                "asian_midpoint_hit_ny": _touches_midpoint(ny, asian_mid),
                "prev_midpoint_hit_london": _touches_midpoint(london, prev_mid),
                "prev_midpoint_hit_ny": _touches_midpoint(ny, prev_mid),
                "asian_distance_london_open": abs(london_open - asian_mid),
                "asian_distance_ny_open": abs(ny_open - asian_mid),
                "prev_distance_london_open": abs(london_open - prev_mid) if pd.notna(prev_mid) else float("nan"),
                "prev_distance_ny_open": abs(ny_open - prev_mid) if pd.notna(prev_mid) else float("nan"),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("No daily rows were produced from input bars")
    return out.sort_values("date").reset_index(drop=True)


def build_distribution(daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metric in [
        "asian_distance_london_open",
        "asian_distance_ny_open",
        "prev_distance_london_open",
        "prev_distance_ny_open",
    ]:
        s = daily[metric]
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _safe_q(s, q)})
    return pd.DataFrame(rows)


def build_summary(daily: pd.DataFrame, dataset_path: str) -> dict[str, object]:
    days = len(daily)
    return {
        "dataset": dataset_path,
        "windows_utc": {
            "asian": {"start": ASIAN_START.strftime("%H:%M"), "end_exclusive": ASIAN_END.strftime("%H:%M")},
            "london": {"start": LONDON_START.strftime("%H:%M"), "end_exclusive": LONDON_END.strftime("%H:%M")},
            "ny": {"start": NY_START.strftime("%H:%M"), "end_exclusive": NY_END.strftime("%H:%M")},
        },
        "days_analyzed": int(days),
        "asian_midpoint_hit_london_frequency": float(daily["asian_midpoint_hit_london"].mean()) if days else 0.0,
        "asian_midpoint_hit_ny_frequency": float(daily["asian_midpoint_hit_ny"].mean()) if days else 0.0,
        "prev_midpoint_hit_london_frequency": float(daily["prev_midpoint_hit_london"].mean()) if days else 0.0,
        "prev_midpoint_hit_ny_frequency": float(daily["prev_midpoint_hit_ny"].mean()) if days else 0.0,
        "median_asian_distance_london_open": _safe_q(daily["asian_distance_london_open"], 0.50),
        "median_prev_distance_london_open": _safe_q(daily["prev_distance_london_open"], 0.50),
    }


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars)
    daily = compute_daily_metrics(bars)
    distribution = build_distribution(daily)
    summary = build_summary(daily, dataset_path=args.bars)

    daily_path = out_dir / "daily_metrics.csv"
    dist_path = out_dir / "distribution.csv"
    summary_path = out_dir / "summary.json"

    daily.to_csv(daily_path, index=False)
    distribution.to_csv(dist_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"asian_midpoint_hit_london_frequency: {summary['asian_midpoint_hit_london_frequency']:.4f}")
    print(f"asian_midpoint_hit_ny_frequency: {summary['asian_midpoint_hit_ny_frequency']:.4f}")
    print(f"prev_midpoint_hit_london_frequency: {summary['prev_midpoint_hit_london_frequency']:.4f}")
    print(f"prev_midpoint_hit_ny_frequency: {summary['prev_midpoint_hit_ny_frequency']:.4f}")

    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
