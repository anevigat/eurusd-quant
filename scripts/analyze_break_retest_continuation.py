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


RANGE_START = time(0, 0)
RANGE_END = time(7, 0)
ANALYSIS_START = time(7, 0)
ANALYSIS_END = time(10, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze break-retest continuation behavior on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/break_retest_continuation_diagnostic",
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


def compute_daily_metrics(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time

    rows: list[dict[str, object]] = []
    for date, day in df.groupby("date", sort=True):
        range_bars = day.loc[_window_mask(day["tod"], RANGE_START, RANGE_END)]
        analysis_bars = day.loc[_window_mask(day["tod"], ANALYSIS_START, ANALYSIS_END)].reset_index(drop=True)
        if range_bars.empty or analysis_bars.empty:
            continue

        asian_high = float(range_bars["mid_high"].max())
        asian_low = float(range_bars["mid_low"].min())
        asian_range = asian_high - asian_low
        if asian_range <= 0:
            continue

        breakout_flag = False
        breakout_direction: str | None = None
        breakout_time: str | None = None
        breakout_level: float | None = None
        breakout_idx: int | None = None

        for idx, row in analysis_bars.iterrows():
            close = float(row["mid_close"])
            if close > asian_high:
                breakout_flag = True
                breakout_direction = "up"
                breakout_time = pd.Timestamp(row["timestamp"]).isoformat()
                breakout_level = asian_high
                breakout_idx = int(idx)
                break
            if close < asian_low:
                breakout_flag = True
                breakout_direction = "down"
                breakout_time = pd.Timestamp(row["timestamp"]).isoformat()
                breakout_level = asian_low
                breakout_idx = int(idx)
                break

        retest_flag = False
        retest_time: str | None = None
        follow_through = pd.NA
        adverse_move = pd.NA
        follow_through_r = pd.NA
        adverse_move_r = pd.NA
        continuation_win_flag = pd.NA

        if breakout_flag and breakout_idx is not None and breakout_level is not None and breakout_direction is not None:
            trailing = analysis_bars.iloc[breakout_idx + 1 :].copy()
            retest_idx: int | None = None
            for idx, row in trailing.iterrows():
                if breakout_direction == "up" and float(row["mid_low"]) <= breakout_level:
                    retest_flag = True
                    retest_idx = int(idx)
                    retest_time = pd.Timestamp(row["timestamp"]).isoformat()
                    break
                if breakout_direction == "down" and float(row["mid_high"]) >= breakout_level:
                    retest_flag = True
                    retest_idx = int(idx)
                    retest_time = pd.Timestamp(row["timestamp"]).isoformat()
                    break

            if retest_flag and retest_idx is not None:
                after_retest = analysis_bars.iloc[retest_idx:].copy()
                if breakout_direction == "up":
                    follow_through = max(0.0, float(after_retest["mid_high"].max()) - breakout_level)
                    adverse_move = max(0.0, breakout_level - float(after_retest["mid_low"].min()))
                else:
                    follow_through = max(0.0, breakout_level - float(after_retest["mid_low"].min()))
                    adverse_move = max(0.0, float(after_retest["mid_high"].max()) - breakout_level)

                follow_through_r = float(follow_through) / asian_range
                adverse_move_r = float(adverse_move) / asian_range
                continuation_win_flag = bool(follow_through > adverse_move)

        rows.append(
            {
                "date": date,
                "asian_high": asian_high,
                "asian_low": asian_low,
                "asian_range": asian_range,
                "breakout_flag": breakout_flag,
                "breakout_direction": breakout_direction,
                "breakout_time": breakout_time,
                "retest_flag": retest_flag,
                "retest_time": retest_time,
                "follow_through": follow_through,
                "adverse_move": adverse_move,
                "follow_through_R": follow_through_r,
                "adverse_move_R": adverse_move_r,
                "continuation_win_flag": continuation_win_flag,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("No daily rows produced from dataset")
    return out


def build_distribution(daily: pd.DataFrame) -> pd.DataFrame:
    retests = daily[daily["retest_flag"]].copy()
    rows: list[dict[str, object]] = []
    for metric in ["follow_through_R", "adverse_move_R"]:
        series = retests[metric]
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _safe_q(series, q)})
    return pd.DataFrame(rows)


def build_summary(daily: pd.DataFrame, dataset_path: str) -> dict[str, object]:
    breakouts = daily[daily["breakout_flag"]]
    retests = daily[daily["retest_flag"]]
    upside_retests = retests[retests["breakout_direction"] == "up"]
    downside_retests = retests[retests["breakout_direction"] == "down"]
    cont = retests["continuation_win_flag"].dropna()

    return {
        "dataset": dataset_path,
        "range_window_utc": {"start": RANGE_START.strftime("%H:%M"), "end_exclusive": RANGE_END.strftime("%H:%M")},
        "analysis_window_utc": {"start": ANALYSIS_START.strftime("%H:%M"), "end_exclusive": ANALYSIS_END.strftime("%H:%M")},
        "days_analyzed": int(len(daily)),
        "breakout_frequency": float(breakouts.shape[0] / len(daily)) if len(daily) else 0.0,
        "retest_frequency_on_breakouts": float(retests.shape[0] / breakouts.shape[0]) if len(breakouts) else 0.0,
        "continuation_probability_after_retest": float(cont.mean()) if len(cont) else 0.0,
        "median_follow_through_R_after_retest": _safe_q(retests["follow_through_R"], 0.50),
        "median_adverse_move_R_after_retest": _safe_q(retests["adverse_move_R"], 0.50),
        "p75_follow_through_R_after_retest": _safe_q(retests["follow_through_R"], 0.75),
        "p90_follow_through_R_after_retest": _safe_q(retests["follow_through_R"], 0.90),
        "upside_retest_frequency": float(len(upside_retests) / len(retests)) if len(retests) else 0.0,
        "downside_retest_frequency": float(len(downside_retests) / len(retests)) if len(retests) else 0.0,
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
    print(f"breakout_frequency: {summary['breakout_frequency']:.4f}")
    print(f"retest_frequency_on_breakouts: {summary['retest_frequency_on_breakouts']:.4f}")
    print(f"continuation_probability_after_retest: {summary['continuation_probability_after_retest']:.4f}")

    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
