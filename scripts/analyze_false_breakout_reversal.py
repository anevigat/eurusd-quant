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
ANALYSIS_END = time(17, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze classical false breakout reversal behavior on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/false_breakout_reversal_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    parser.add_argument(
        "--return-inside-bars",
        type=int,
        default=4,
        help="Bars allowed for breakout to return inside range",
    )
    parser.add_argument(
        "--reversal-horizon-bars",
        type=int,
        default=8,
        help="Bars after return-inside for reversal/adverse measurement",
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


def _find_false_break(
    bars: pd.DataFrame,
    range_high: float,
    range_low: float,
    return_inside_bars: int,
) -> tuple[int, str, int] | None:
    for idx, row in bars.iterrows():
        high = float(row["mid_high"])
        low = float(row["mid_low"])
        if high > range_high:
            upper = min(idx + return_inside_bars + 1, len(bars))
            for j in range(idx + 1, upper):
                if float(bars.iloc[j]["mid_close"]) < range_high:
                    return idx, "false_break_up", j
        if low < range_low:
            upper = min(idx + return_inside_bars + 1, len(bars))
            for j in range(idx + 1, upper):
                if float(bars.iloc[j]["mid_close"]) > range_low:
                    return idx, "false_break_down", j
    return None


def compute_daily_metrics(
    bars: pd.DataFrame,
    return_inside_bars: int,
    reversal_horizon_bars: int,
) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time

    rows: list[dict[str, object]] = []
    for date, day in df.groupby("date", sort=True):
        range_bars = day.loc[_window_mask(day["tod"], RANGE_START, RANGE_END)]
        analysis = day.loc[_window_mask(day["tod"], ANALYSIS_START, ANALYSIS_END)].reset_index(drop=True)
        if range_bars.empty or analysis.empty:
            continue

        range_high = float(range_bars["mid_high"].max())
        range_low = float(range_bars["mid_low"].min())
        range_size = range_high - range_low
        if range_size <= 0:
            continue

        event = _find_false_break(
            analysis,
            range_high=range_high,
            range_low=range_low,
            return_inside_bars=return_inside_bars,
        )

        false_break_flag = False
        false_break_direction: str | None = None
        break_time: str | None = None
        return_inside_time: str | None = None
        follow_through_r = pd.NA
        adverse_move_r = pd.NA
        reversal_win_flag = pd.NA

        if event is not None:
            break_idx, false_break_direction, return_idx = event
            false_break_flag = True
            break_time = pd.Timestamp(analysis.iloc[break_idx]["timestamp"]).isoformat()
            return_inside_time = pd.Timestamp(analysis.iloc[return_idx]["timestamp"]).isoformat()
            entry = float(analysis.iloc[return_idx]["mid_close"])
            horizon = analysis.iloc[return_idx + 1 : return_idx + 1 + reversal_horizon_bars]
            if not horizon.empty and false_break_direction is not None:
                if false_break_direction == "false_break_up":
                    follow = max(0.0, entry - float(horizon["mid_low"].min()))
                    adverse = max(0.0, float(horizon["mid_high"].max()) - entry)
                else:
                    follow = max(0.0, float(horizon["mid_high"].max()) - entry)
                    adverse = max(0.0, entry - float(horizon["mid_low"].min()))
                follow_through_r = follow / range_size
                adverse_move_r = adverse / range_size
                reversal_win_flag = bool(follow > adverse)

        rows.append(
            {
                "date": date,
                "range_high": range_high,
                "range_low": range_low,
                "range_size": range_size,
                "false_break_flag": false_break_flag,
                "false_break_direction": false_break_direction,
                "break_time": break_time,
                "return_inside_time": return_inside_time,
                "follow_through_R": follow_through_r,
                "adverse_move_R": adverse_move_r,
                "reversal_win_flag": reversal_win_flag,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("No daily rows produced from dataset")
    return out


def build_distribution(daily: pd.DataFrame) -> pd.DataFrame:
    events = daily[daily["false_break_flag"]]
    rows: list[dict[str, object]] = []
    for metric in ["follow_through_R", "adverse_move_R"]:
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _safe_q(events[metric], q)})
    return pd.DataFrame(rows)


def build_summary(
    daily: pd.DataFrame,
    dataset_path: str,
    return_inside_bars: int,
    reversal_horizon_bars: int,
) -> dict[str, object]:
    events = daily[daily["false_break_flag"]]
    wins = events["reversal_win_flag"].dropna()
    return {
        "dataset": dataset_path,
        "range_window_utc": {"start": RANGE_START.strftime("%H:%M"), "end_exclusive": RANGE_END.strftime("%H:%M")},
        "analysis_window_utc": {"start": ANALYSIS_START.strftime("%H:%M"), "end_exclusive": ANALYSIS_END.strftime("%H:%M")},
        "return_inside_bars": return_inside_bars,
        "reversal_horizon_bars": reversal_horizon_bars,
        "days_analyzed": int(len(daily)),
        "false_break_frequency": float(len(events) / len(daily)) if len(daily) else 0.0,
        "reversal_probability": float(wins.mean()) if len(wins) else 0.0,
        "median_follow_through_R": _safe_q(events["follow_through_R"], 0.50),
        "median_adverse_move_R": _safe_q(events["adverse_move_R"], 0.50),
    }


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars)
    daily = compute_daily_metrics(
        bars,
        return_inside_bars=args.return_inside_bars,
        reversal_horizon_bars=args.reversal_horizon_bars,
    )
    distribution = build_distribution(daily)
    summary = build_summary(
        daily,
        dataset_path=args.bars,
        return_inside_bars=args.return_inside_bars,
        reversal_horizon_bars=args.reversal_horizon_bars,
    )

    daily_path = out_dir / "daily_metrics.csv"
    dist_path = out_dir / "distribution.csv"
    summary_path = out_dir / "summary.json"
    daily.to_csv(daily_path, index=False)
    distribution.to_csv(dist_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"false_break_frequency: {summary['false_break_frequency']:.4f}")
    print(f"reversal_probability: {summary['reversal_probability']:.4f}")
    print(f"median_follow_through_R: {summary['median_follow_through_R']:.4f}")
    print(f"median_adverse_move_R: {summary['median_adverse_move_R']:.4f}")
    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
