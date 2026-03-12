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


ANALYSIS_START = time(7, 0)
ANALYSIS_END = time(17, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze prior-day liquidity sweep reversal behavior on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/liquidity_sweep_reversal_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    parser.add_argument(
        "--return-inside-bars",
        type=int,
        default=4,
        help="Bars allowed for sweep return-inside confirmation",
    )
    parser.add_argument(
        "--reversal-horizon-bars",
        type=int,
        default=8,
        help="Bars after return-inside to measure follow-through/adverse excursion",
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


def _find_sweep_event(
    day_bars: pd.DataFrame,
    prev_day_high: float,
    prev_day_low: float,
    return_inside_bars: int,
) -> tuple[int, str, int] | None:
    for idx, row in day_bars.iterrows():
        high = float(row["mid_high"])
        low = float(row["mid_low"])
        if high > prev_day_high:
            upper = min(idx + return_inside_bars + 1, len(day_bars))
            for j in range(idx + 1, upper):
                if float(day_bars.iloc[j]["mid_close"]) < prev_day_high:
                    return idx, "sweep_up", j
        if low < prev_day_low:
            upper = min(idx + return_inside_bars + 1, len(day_bars))
            for j in range(idx + 1, upper):
                if float(day_bars.iloc[j]["mid_close"]) > prev_day_low:
                    return idx, "sweep_down", j
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

    days = list(df.groupby("date", sort=True))
    rows: list[dict[str, object]] = []

    for i in range(1, len(days)):
        date, day_bars_full = days[i]
        _, prev_day_bars = days[i - 1]
        day_bars = day_bars_full.loc[
            _window_mask(day_bars_full["tod"], ANALYSIS_START, ANALYSIS_END)
        ].reset_index(drop=True)
        if day_bars.empty:
            continue

        prev_day_high = float(prev_day_bars["mid_high"].max())
        prev_day_low = float(prev_day_bars["mid_low"].min())
        prev_day_range = prev_day_high - prev_day_low
        if prev_day_range <= 0:
            continue

        event = _find_sweep_event(
            day_bars,
            prev_day_high=prev_day_high,
            prev_day_low=prev_day_low,
            return_inside_bars=return_inside_bars,
        )

        sweep_flag = False
        sweep_direction: str | None = None
        sweep_time: str | None = None
        return_inside_time: str | None = None
        follow_through_r = pd.NA
        adverse_move_r = pd.NA
        reversal_win_flag = pd.NA

        if event is not None:
            sweep_idx, sweep_direction, return_idx = event
            sweep_flag = True
            sweep_time = pd.Timestamp(day_bars.iloc[sweep_idx]["timestamp"]).isoformat()
            return_inside_time = pd.Timestamp(day_bars.iloc[return_idx]["timestamp"]).isoformat()
            entry = float(day_bars.iloc[return_idx]["mid_close"])
            horizon = day_bars.iloc[return_idx + 1 : return_idx + 1 + reversal_horizon_bars]

            if not horizon.empty and sweep_direction is not None:
                if sweep_direction == "sweep_up":
                    follow = max(0.0, entry - float(horizon["mid_low"].min()))
                    adverse = max(0.0, float(horizon["mid_high"].max()) - entry)
                else:
                    follow = max(0.0, float(horizon["mid_high"].max()) - entry)
                    adverse = max(0.0, entry - float(horizon["mid_low"].min()))
                follow_through_r = follow / prev_day_range
                adverse_move_r = adverse / prev_day_range
                reversal_win_flag = bool(follow > adverse)

        rows.append(
            {
                "date": date,
                "prev_day_high": prev_day_high,
                "prev_day_low": prev_day_low,
                "prev_day_range": prev_day_range,
                "sweep_flag": sweep_flag,
                "sweep_direction": sweep_direction,
                "sweep_time": sweep_time,
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
    sweeps = daily[daily["sweep_flag"]]
    rows: list[dict[str, object]] = []
    for metric in ["follow_through_R", "adverse_move_R"]:
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _safe_q(sweeps[metric], q)})
    return pd.DataFrame(rows)


def build_summary(
    daily: pd.DataFrame,
    dataset_path: str,
    return_inside_bars: int,
    reversal_horizon_bars: int,
) -> dict[str, object]:
    sweeps = daily[daily["sweep_flag"]]
    up = sweeps[sweeps["sweep_direction"] == "sweep_up"]
    down = sweeps[sweeps["sweep_direction"] == "sweep_down"]
    wins = sweeps["reversal_win_flag"].dropna()

    return {
        "dataset": dataset_path,
        "analysis_window_utc": {"start": ANALYSIS_START.strftime("%H:%M"), "end_exclusive": ANALYSIS_END.strftime("%H:%M")},
        "return_inside_bars": return_inside_bars,
        "reversal_horizon_bars": reversal_horizon_bars,
        "days_analyzed": int(len(daily)),
        "sweep_frequency": float(len(sweeps) / len(daily)) if len(daily) else 0.0,
        "bullish_sweep_frequency": float(len(down) / len(sweeps)) if len(sweeps) else 0.0,
        "bearish_sweep_frequency": float(len(up) / len(sweeps)) if len(sweeps) else 0.0,
        "reversal_probability": float(wins.mean()) if len(wins) else 0.0,
        "median_follow_through_R": _safe_q(sweeps["follow_through_R"], 0.50),
        "median_adverse_move_R": _safe_q(sweeps["adverse_move_R"], 0.50),
        "p75_follow_through_R": _safe_q(sweeps["follow_through_R"], 0.75),
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
    print(f"sweep_frequency: {summary['sweep_frequency']:.4f}")
    print(f"reversal_probability: {summary['reversal_probability']:.4f}")
    print(f"median_follow_through_R: {summary['median_follow_through_R']:.4f}")
    print(f"median_adverse_move_R: {summary['median_adverse_move_R']:.4f}")
    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
