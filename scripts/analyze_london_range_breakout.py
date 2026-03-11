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
PIP_SIZE = 0.0001


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze London Opening Range Breakout behavior on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/london_range_breakout_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, and range_distribution.csv",
    )
    return parser.parse_args()


def _window_mask(series: pd.Series, start: time, end: time) -> pd.Series:
    if start <= end:
        return (series >= start) & (series < end)
    return (series >= start) | (series < end)


def detect_breakout(
    london: pd.DataFrame,
    asian_high: float,
    asian_low: float,
) -> tuple[bool, bool, str, pd.Timestamp | pd.NaT]:
    above_hits = london.loc[london["mid_high"] > asian_high, "timestamp"]
    below_hits = london.loc[london["mid_low"] < asian_low, "timestamp"]

    break_above = not above_hits.empty
    break_below = not below_hits.empty

    if not break_above and not break_below:
        return False, False, "none", pd.NaT

    above_time = above_hits.iloc[0] if break_above else pd.NaT
    below_time = below_hits.iloc[0] if break_below else pd.NaT

    if break_above and (not break_below or above_time < below_time):
        return break_above, break_below, "above", above_time
    if break_below and (not break_above or below_time < above_time):
        return break_above, break_below, "below", below_time
    return break_above, break_below, "both", above_time


def compute_follow_through(
    london: pd.DataFrame,
    asian_high: float,
    asian_low: float,
    first_break_direction: str,
    break_time: pd.Timestamp | pd.NaT,
) -> tuple[float, float]:
    if first_break_direction not in {"above", "below"} or pd.isna(break_time):
        return float("nan"), float("nan")

    post_break = london.loc[london["timestamp"] >= break_time]
    if post_break.empty:
        return float("nan"), float("nan")

    if first_break_direction == "above":
        follow = float(post_break["mid_high"].max() - asian_high)
        adverse = float(asian_high - post_break["mid_low"].min())
    else:
        follow = float(asian_low - post_break["mid_low"].min())
        adverse = float(post_break["mid_high"].max() - asian_low)

    return max(follow, 0.0), max(adverse, 0.0)


def compute_daily_metrics(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time

    daily_rows: list[dict[str, object]] = []

    for date, day in df.groupby("date", sort=True):
        asian = day.loc[_window_mask(day["tod"], ASIAN_START, ASIAN_END)]
        london = day.loc[_window_mask(day["tod"], LONDON_START, LONDON_END), ["timestamp", "mid_high", "mid_low"]]

        if asian.empty or london.empty:
            continue

        asian_high = float(asian["mid_high"].max())
        asian_low = float(asian["mid_low"].min())
        asian_range = float(asian_high - asian_low)

        break_above, break_below, first_direction, break_time = detect_breakout(
            london=london,
            asian_high=asian_high,
            asian_low=asian_low,
        )
        max_move_after_break, max_adverse_move = compute_follow_through(
            london=london,
            asian_high=asian_high,
            asian_low=asian_low,
            first_break_direction=first_direction,
            break_time=break_time,
        )

        if asian_range > 0.0 and pd.notna(max_move_after_break):
            follow_r = float(max_move_after_break / asian_range)
            adverse_r = float(max_adverse_move / asian_range)
        else:
            follow_r = float("nan")
            adverse_r = float("nan")

        daily_rows.append(
            {
                "date": date,
                "asian_high": asian_high,
                "asian_low": asian_low,
                "asian_range": asian_range,
                "asian_range_pips": float(asian_range / PIP_SIZE),
                "break_above_range": bool(break_above),
                "break_below_range": bool(break_below),
                "first_break_direction": first_direction,
                "break_time": break_time.isoformat() if pd.notna(break_time) else None,
                "max_move_after_break": max_move_after_break,
                "max_adverse_move": max_adverse_move,
                "follow_through_R": follow_r,
                "adverse_move_R": adverse_r,
            }
        )

    out = pd.DataFrame(daily_rows)
    if out.empty:
        raise ValueError("No daily rows were produced from the input bars")
    return out.sort_values("date").reset_index(drop=True)


def build_range_distribution(daily: pd.DataFrame) -> pd.DataFrame:
    series = daily["asian_range"]
    quantiles = {
        "min": float(series.min()),
        "p10": float(series.quantile(0.10)),
        "p25": float(series.quantile(0.25)),
        "p50": float(series.quantile(0.50)),
        "p75": float(series.quantile(0.75)),
        "p90": float(series.quantile(0.90)),
        "p95": float(series.quantile(0.95)),
        "max": float(series.max()),
        "mean": float(series.mean()),
    }

    rows = [
        {
            "stat": stat,
            "asian_range": value,
            "asian_range_pips": float(value / PIP_SIZE),
        }
        for stat, value in quantiles.items()
    ]
    return pd.DataFrame(rows)


def _safe_quantile(series: pd.Series, q: float) -> float:
    if series.empty:
        return 0.0
    return float(series.quantile(q))


def build_summary(daily: pd.DataFrame, dataset_path: str) -> dict[str, object]:
    days_analyzed = int(len(daily))
    any_break = daily["break_above_range"] | daily["break_below_range"]
    breakout_days = int(any_break.sum())

    directional = daily[daily["first_break_direction"].isin(["above", "below"])]
    follow = directional["follow_through_R"].dropna()
    adverse = directional["adverse_move_R"].dropna()

    return {
        "dataset": dataset_path,
        "windows_utc": {
            "asian": {"start": ASIAN_START.strftime("%H:%M"), "end_exclusive": ASIAN_END.strftime("%H:%M")},
            "london": {"start": LONDON_START.strftime("%H:%M"), "end_exclusive": LONDON_END.strftime("%H:%M")},
        },
        "days_analyzed": days_analyzed,
        "breakout_days": breakout_days,
        "breakout_frequency": float(breakout_days / days_analyzed) if days_analyzed else 0.0,
        "break_above_frequency": float(daily["break_above_range"].mean()) if days_analyzed else 0.0,
        "break_below_frequency": float(daily["break_below_range"].mean()) if days_analyzed else 0.0,
        "median_follow_through_R": _safe_quantile(follow, 0.50),
        "p75_follow_through_R": _safe_quantile(follow, 0.75),
        "p90_follow_through_R": _safe_quantile(follow, 0.90),
        "median_adverse_move_R": _safe_quantile(adverse, 0.50),
    }


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars)
    daily = compute_daily_metrics(bars)
    range_distribution = build_range_distribution(daily)
    summary = build_summary(daily, dataset_path=args.bars)

    daily_path = output_dir / "daily_metrics.csv"
    range_distribution_path = output_dir / "range_distribution.csv"
    summary_path = output_dir / "summary.json"

    daily.to_csv(daily_path, index=False)
    range_distribution.to_csv(range_distribution_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"breakout_frequency: {summary['breakout_frequency']:.4f}")
    print(f"break_above_frequency: {summary['break_above_frequency']:.4f}")
    print(f"break_below_frequency: {summary['break_below_frequency']:.4f}")
    print(f"median_follow_through_R: {summary['median_follow_through_R']:.4f}")
    print(f"p75_follow_through_R: {summary['p75_follow_through_R']:.4f}")
    print(f"p90_follow_through_R: {summary['p90_follow_through_R']:.4f}")
    print(f"median_adverse_move_R: {summary['median_adverse_move_R']:.4f}")

    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved range distribution: {range_distribution_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
