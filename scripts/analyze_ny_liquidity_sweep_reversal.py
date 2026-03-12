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


LONDON_START = time(7, 0)
LONDON_END = time(13, 0)
NY_START = time(13, 0)
NY_END = time(16, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze NY liquidity sweep reversal vs London range on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/ny_liquidity_sweep_reversal_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    return parser.parse_args()


def _window_mask(series: pd.Series, start: time, end: time) -> pd.Series:
    if start <= end:
        return (series >= start) & (series < end)
    return (series >= start) | (series < end)


def _q(series: pd.Series, q: float) -> float:
    clean = series.dropna()
    if clean.empty:
        return 0.0
    return float(clean.quantile(q))


def compute_daily_metrics(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time

    rows: list[dict[str, object]] = []
    for date, day in df.groupby("date", sort=True):
        london = day.loc[_window_mask(day["tod"], LONDON_START, LONDON_END)]
        ny = day.loc[_window_mask(day["tod"], NY_START, NY_END)]
        if london.empty or ny.empty:
            continue

        london_high = float(london["mid_high"].max())
        london_low = float(london["mid_low"].min())
        london_range = london_high - london_low

        above_hits = ny.loc[ny["mid_high"] > london_high, "timestamp"]
        below_hits = ny.loc[ny["mid_low"] < london_low, "timestamp"]

        sweep_above = not above_hits.empty
        sweep_below = not below_hits.empty

        if not sweep_above and not sweep_below:
            rows.append(
                {
                    "date": date,
                    "london_high": london_high,
                    "london_low": london_low,
                    "london_range": london_range,
                    "sweep_detected": False,
                    "sweep_direction": "none",
                    "sweep_time": None,
                    "reversal_move": float("nan"),
                    "continuation_move": float("nan"),
                    "reversal_ratio": float("nan"),
                    "follow_through_ratio": float("nan"),
                }
            )
            continue

        above_time = above_hits.iloc[0] if sweep_above else pd.NaT
        below_time = below_hits.iloc[0] if sweep_below else pd.NaT

        if sweep_above and (not sweep_below or above_time <= below_time):
            direction = "above"
            sweep_time = above_time
            sweep_level = london_high
        else:
            direction = "below"
            sweep_time = below_time
            sweep_level = london_low

        post = ny.loc[ny["timestamp"] >= sweep_time]
        if direction == "above":
            reversal_move = max(0.0, sweep_level - float(post["mid_low"].min()))
            continuation_move = max(0.0, float(post["mid_high"].max()) - sweep_level)
        else:
            reversal_move = max(0.0, float(post["mid_high"].max()) - sweep_level)
            continuation_move = max(0.0, sweep_level - float(post["mid_low"].min()))

        if london_range > 0:
            reversal_ratio = reversal_move / london_range
            follow_through_ratio = continuation_move / london_range
        else:
            reversal_ratio = float("nan")
            follow_through_ratio = float("nan")

        rows.append(
            {
                "date": date,
                "london_high": london_high,
                "london_low": london_low,
                "london_range": london_range,
                "sweep_detected": True,
                "sweep_direction": direction,
                "sweep_time": sweep_time.isoformat(),
                "reversal_move": reversal_move,
                "continuation_move": continuation_move,
                "reversal_ratio": reversal_ratio,
                "follow_through_ratio": follow_through_ratio,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("No daily rows were produced from input bars")
    return out.sort_values("date").reset_index(drop=True)


def build_distribution(daily: pd.DataFrame) -> pd.DataFrame:
    swept = daily[daily["sweep_detected"]]
    rows: list[dict[str, object]] = []
    for metric in ["reversal_ratio", "follow_through_ratio"]:
        s = swept[metric]
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _q(s, q)})
    return pd.DataFrame(rows)


def build_summary(daily: pd.DataFrame, dataset_path: str) -> dict[str, object]:
    days = len(daily)
    swept = daily[daily["sweep_detected"]]
    reversal_dom = (swept["reversal_ratio"] > swept["follow_through_ratio"]).dropna()

    return {
        "dataset": dataset_path,
        "windows_utc": {
            "london_reference": {"start": LONDON_START.strftime("%H:%M"), "end_exclusive": LONDON_END.strftime("%H:%M")},
            "ny_sweep": {"start": NY_START.strftime("%H:%M"), "end_exclusive": NY_END.strftime("%H:%M")},
        },
        "days_analyzed": int(days),
        "sweep_frequency": float(len(swept) / days) if days else 0.0,
        "sweep_above_frequency": float((swept["sweep_direction"] == "above").mean()) if not swept.empty else 0.0,
        "sweep_below_frequency": float((swept["sweep_direction"] == "below").mean()) if not swept.empty else 0.0,
        "median_reversal_ratio": _q(swept["reversal_ratio"], 0.50),
        "p75_reversal_ratio": _q(swept["reversal_ratio"], 0.75),
        "median_follow_through_ratio": _q(swept["follow_through_ratio"], 0.50),
        "reversal_dominates_frequency": float(reversal_dom.mean()) if not reversal_dom.empty else 0.0,
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
    print(f"sweep_frequency: {summary['sweep_frequency']:.4f}")
    print(f"sweep_above_frequency: {summary['sweep_above_frequency']:.4f}")
    print(f"sweep_below_frequency: {summary['sweep_below_frequency']:.4f}")
    print(f"median_reversal_ratio: {summary['median_reversal_ratio']:.4f}")
    print(f"median_follow_through_ratio: {summary['median_follow_through_ratio']:.4f}")
    print(f"reversal_dominates_frequency: {summary['reversal_dominates_frequency']:.4f}")

    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
