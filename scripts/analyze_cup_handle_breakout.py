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
        description="Analyze cup-and-handle breakout behavior on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/cup_handle_breakout_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    parser.add_argument("--atr-period", type=int, default=14, help="ATR period")
    parser.add_argument(
        "--min-cup-depth-atr",
        type=float,
        default=0.8,
        help="Cup depth must be at least this ATR multiple",
    )
    parser.add_argument(
        "--rim-tolerance-atr",
        type=float,
        default=0.4,
        help="Left/right cup rims must be within this ATR multiple",
    )
    parser.add_argument(
        "--max-handle-depth-ratio",
        type=float,
        default=0.5,
        help="Handle pullback depth relative to cup depth",
    )
    parser.add_argument(
        "--handle-max-bars",
        type=int,
        default=6,
        help="Max bars between right rim and breakout",
    )
    parser.add_argument(
        "--follow-horizon-bars",
        type=int,
        default=8,
        help="Bars after breakout to measure follow-through/adverse move",
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


def _compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
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


def _swing_highs(bars: pd.DataFrame) -> list[int]:
    out: list[int] = []
    for i in range(1, len(bars) - 1):
        if bars.iloc[i]["mid_high"] > bars.iloc[i - 1]["mid_high"] and bars.iloc[i]["mid_high"] >= bars.iloc[i + 1]["mid_high"]:
            out.append(i)
    return out


def _swing_lows(bars: pd.DataFrame) -> list[int]:
    out: list[int] = []
    for i in range(1, len(bars) - 1):
        if bars.iloc[i]["mid_low"] < bars.iloc[i - 1]["mid_low"] and bars.iloc[i]["mid_low"] <= bars.iloc[i + 1]["mid_low"]:
            out.append(i)
    return out


def _detect_cup_handle(
    bars: pd.DataFrame,
    min_cup_depth_atr: float,
    rim_tolerance_atr: float,
    max_handle_depth_ratio: float,
    handle_max_bars: int,
    follow_horizon_bars: int,
) -> dict[str, object] | None:
    n = len(bars)
    if n < 12:
        return None

    highs = _swing_highs(bars)
    lows = _swing_lows(bars)
    for i in range(len(highs) - 1):
        left_idx = highs[i]
        left_high = float(bars.iloc[left_idx]["mid_high"])
        for j in range(i + 1, len(highs)):
            right_idx = highs[j]
            if right_idx - left_idx < 4:
                continue
            if right_idx >= n - 3:
                continue

            between_lows = [idx for idx in lows if left_idx < idx < right_idx]
            if not between_lows:
                continue
            cup_idx = min(between_lows, key=lambda idx: float(bars.iloc[idx]["mid_low"]))
            cup_low = float(bars.iloc[cup_idx]["mid_low"])
            cup_pos = cup_idx / max(1, n - 1)
            if cup_pos < 0.2 or cup_pos > 0.8:
                continue

            right_high = float(bars.iloc[right_idx]["mid_high"])
            atr = float(bars.iloc[right_idx]["atr"]) if pd.notna(bars.iloc[right_idx]["atr"]) else 0.0
            if atr <= 0:
                continue
            if abs(left_high - right_high) > rim_tolerance_atr * atr:
                continue

            cup_depth = ((left_high + right_high) / 2.0) - cup_low
            if cup_depth <= 0:
                continue
            if cup_depth < min_cup_depth_atr * atr:
                continue

            resistance = max(left_high, right_high)
            handle_end = min(n, right_idx + 1 + handle_max_bars)
            if right_idx + 1 >= handle_end:
                continue
            handle_slice = bars.iloc[right_idx + 1 : handle_end]
            if handle_slice.empty:
                continue
            handle_low = float(handle_slice["mid_low"].min())
            handle_depth = resistance - handle_low
            if handle_depth < 0:
                continue
            if handle_depth > max_handle_depth_ratio * cup_depth:
                continue

            break_idx: int | None = None
            for b in range(right_idx + 1, handle_end):
                if float(bars.iloc[b]["mid_close"]) > resistance:
                    break_idx = b
                    break
            if break_idx is None:
                continue

            post = bars.iloc[break_idx + 1 : break_idx + 1 + follow_horizon_bars]
            if post.empty:
                continue
            breakout_close = float(bars.iloc[break_idx]["mid_close"])
            follow = max(0.0, float(post["mid_high"].max()) - breakout_close)
            adverse = max(0.0, breakout_close - float(post["mid_low"].min()))

            return {
                "pattern_flag": True,
                "breakout_time": pd.Timestamp(bars.iloc[break_idx]["timestamp"]).isoformat(),
                "cup_depth": cup_depth,
                "breakout_follow_through_ratio": follow / cup_depth,
                "adverse_move_ratio": adverse / cup_depth,
                "breakout_win_flag": bool(follow > adverse),
            }
    return None


def compute_daily_metrics(
    bars: pd.DataFrame,
    atr_period: int,
    min_cup_depth_atr: float,
    rim_tolerance_atr: float,
    max_handle_depth_ratio: float,
    handle_max_bars: int,
    follow_horizon_bars: int,
) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["atr"] = _compute_atr(df, period=atr_period)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time

    rows: list[dict[str, object]] = []
    for date, day in df.groupby("date", sort=True):
        session = day.loc[_window_mask(day["tod"], ANALYSIS_START, ANALYSIS_END)].reset_index(drop=True)
        if len(session) < 12:
            continue
        event = _detect_cup_handle(
            session,
            min_cup_depth_atr=min_cup_depth_atr,
            rim_tolerance_atr=rim_tolerance_atr,
            max_handle_depth_ratio=max_handle_depth_ratio,
            handle_max_bars=handle_max_bars,
            follow_horizon_bars=follow_horizon_bars,
        )
        if event is None:
            rows.append(
                {
                    "date": date,
                    "pattern_flag": False,
                    "breakout_time": None,
                    "cup_depth": pd.NA,
                    "breakout_follow_through_ratio": pd.NA,
                    "adverse_move_ratio": pd.NA,
                    "breakout_win_flag": pd.NA,
                }
            )
        else:
            rows.append({"date": date, **event})

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("No daily rows produced from dataset")
    return out


def build_distribution(daily: pd.DataFrame) -> pd.DataFrame:
    events = daily[daily["pattern_flag"]]
    rows: list[dict[str, object]] = []
    for metric in ["breakout_follow_through_ratio", "adverse_move_ratio"]:
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _safe_q(events[metric], q)})
    return pd.DataFrame(rows)


def build_summary(
    daily: pd.DataFrame,
    dataset_path: str,
    atr_period: int,
    min_cup_depth_atr: float,
    rim_tolerance_atr: float,
    max_handle_depth_ratio: float,
    handle_max_bars: int,
    follow_horizon_bars: int,
) -> dict[str, object]:
    events = daily[daily["pattern_flag"]]
    wins = events["breakout_win_flag"].dropna()
    return {
        "dataset": dataset_path,
        "analysis_window_utc": {"start": ANALYSIS_START.strftime("%H:%M"), "end_exclusive": ANALYSIS_END.strftime("%H:%M")},
        "atr_period": atr_period,
        "min_cup_depth_atr": min_cup_depth_atr,
        "rim_tolerance_atr": rim_tolerance_atr,
        "max_handle_depth_ratio": max_handle_depth_ratio,
        "handle_max_bars": handle_max_bars,
        "follow_horizon_bars": follow_horizon_bars,
        "days_analyzed": int(len(daily)),
        "pattern_frequency": float(len(events) / len(daily)) if len(daily) else 0.0,
        "breakout_success_probability": float(wins.mean()) if len(wins) else 0.0,
        "median_breakout_follow_through_ratio": _safe_q(events["breakout_follow_through_ratio"], 0.50),
        "median_adverse_move_ratio": _safe_q(events["adverse_move_ratio"], 0.50),
    }


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars)
    daily = compute_daily_metrics(
        bars,
        atr_period=args.atr_period,
        min_cup_depth_atr=args.min_cup_depth_atr,
        rim_tolerance_atr=args.rim_tolerance_atr,
        max_handle_depth_ratio=args.max_handle_depth_ratio,
        handle_max_bars=args.handle_max_bars,
        follow_horizon_bars=args.follow_horizon_bars,
    )
    distribution = build_distribution(daily)
    summary = build_summary(
        daily,
        dataset_path=args.bars,
        atr_period=args.atr_period,
        min_cup_depth_atr=args.min_cup_depth_atr,
        rim_tolerance_atr=args.rim_tolerance_atr,
        max_handle_depth_ratio=args.max_handle_depth_ratio,
        handle_max_bars=args.handle_max_bars,
        follow_horizon_bars=args.follow_horizon_bars,
    )

    daily_path = out_dir / "daily_metrics.csv"
    dist_path = out_dir / "distribution.csv"
    summary_path = out_dir / "summary.json"
    daily.to_csv(daily_path, index=False)
    distribution.to_csv(dist_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"pattern_frequency: {summary['pattern_frequency']:.4f}")
    print(f"breakout_success_probability: {summary['breakout_success_probability']:.4f}")
    print(f"median_breakout_follow_through_ratio: {summary['median_breakout_follow_through_ratio']:.4f}")
    print(f"median_adverse_move_ratio: {summary['median_adverse_move_ratio']:.4f}")
    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
