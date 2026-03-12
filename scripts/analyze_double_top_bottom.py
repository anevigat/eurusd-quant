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
        description="Analyze double top / double bottom reversal patterns on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/double_top_bottom_reversal_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    parser.add_argument("--atr-period", type=int, default=14, help="ATR period")
    parser.add_argument(
        "--peak-tolerance-atr",
        type=float,
        default=0.3,
        help="Allowed ATR multiple between peak1 and peak2 (or bottom1 and bottom2)",
    )
    parser.add_argument(
        "--min-pullback-atr",
        type=float,
        default=0.5,
        help="Minimum pullback depth in ATR before neckline break",
    )
    parser.add_argument(
        "--reversal-horizon-bars",
        type=int,
        default=8,
        help="Bars after neckline break for follow-through/adverse measurement",
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
    idxs: list[int] = []
    for i in range(1, len(bars) - 1):
        if bars.iloc[i]["mid_high"] > bars.iloc[i - 1]["mid_high"] and bars.iloc[i]["mid_high"] >= bars.iloc[i + 1]["mid_high"]:
            idxs.append(i)
    return idxs


def _swing_lows(bars: pd.DataFrame) -> list[int]:
    idxs: list[int] = []
    for i in range(1, len(bars) - 1):
        if bars.iloc[i]["mid_low"] < bars.iloc[i - 1]["mid_low"] and bars.iloc[i]["mid_low"] <= bars.iloc[i + 1]["mid_low"]:
            idxs.append(i)
    return idxs


def _detect_double_top(
    bars: pd.DataFrame,
    highs: list[int],
    tol_atr: float,
    min_pullback_atr: float,
    horizon: int,
) -> dict[str, object] | None:
    for i in range(len(highs) - 1):
        h1_idx = highs[i]
        for j in range(i + 1, len(highs)):
            h2_idx = highs[j]
            if h2_idx - h1_idx < 2:
                continue

            h1 = float(bars.iloc[h1_idx]["mid_high"])
            h2 = float(bars.iloc[h2_idx]["mid_high"])
            atr = float(bars.iloc[h2_idx]["atr"]) if pd.notna(bars.iloc[h2_idx]["atr"]) else 0.0
            if atr <= 0:
                continue
            if abs(h1 - h2) > tol_atr * atr:
                continue

            valley = float(bars.iloc[h1_idx + 1 : h2_idx]["mid_low"].min())
            if min(h1, h2) - valley < min_pullback_atr * atr:
                continue

            neckline = valley
            break_idx: int | None = None
            for k in range(h2_idx + 1, len(bars)):
                if float(bars.iloc[k]["mid_close"]) < neckline:
                    break_idx = k
                    break
            if break_idx is None:
                continue

            pattern_height = ((h1 + h2) / 2.0) - neckline
            if pattern_height <= 0:
                continue
            post = bars.iloc[break_idx + 1 : break_idx + 1 + horizon]
            if post.empty:
                continue

            follow = max(0.0, neckline - float(post["mid_low"].min()))
            adverse = max(0.0, float(post["mid_high"].max()) - neckline)
            return {
                "pattern_flag": True,
                "pattern_type": "double_top",
                "break_time": pd.Timestamp(bars.iloc[break_idx]["timestamp"]).isoformat(),
                "follow_through_R": follow / pattern_height,
                "adverse_move_R": adverse / pattern_height,
                "reversal_win_flag": bool(follow > adverse),
            }
    return None


def _detect_double_bottom(
    bars: pd.DataFrame,
    lows: list[int],
    tol_atr: float,
    min_pullback_atr: float,
    horizon: int,
) -> dict[str, object] | None:
    for i in range(len(lows) - 1):
        l1_idx = lows[i]
        for j in range(i + 1, len(lows)):
            l2_idx = lows[j]
            if l2_idx - l1_idx < 2:
                continue

            l1 = float(bars.iloc[l1_idx]["mid_low"])
            l2 = float(bars.iloc[l2_idx]["mid_low"])
            atr = float(bars.iloc[l2_idx]["atr"]) if pd.notna(bars.iloc[l2_idx]["atr"]) else 0.0
            if atr <= 0:
                continue
            if abs(l1 - l2) > tol_atr * atr:
                continue

            crest = float(bars.iloc[l1_idx + 1 : l2_idx]["mid_high"].max())
            if crest - max(l1, l2) < min_pullback_atr * atr:
                continue

            neckline = crest
            break_idx: int | None = None
            for k in range(l2_idx + 1, len(bars)):
                if float(bars.iloc[k]["mid_close"]) > neckline:
                    break_idx = k
                    break
            if break_idx is None:
                continue

            pattern_height = neckline - ((l1 + l2) / 2.0)
            if pattern_height <= 0:
                continue
            post = bars.iloc[break_idx + 1 : break_idx + 1 + horizon]
            if post.empty:
                continue

            follow = max(0.0, float(post["mid_high"].max()) - neckline)
            adverse = max(0.0, neckline - float(post["mid_low"].min()))
            return {
                "pattern_flag": True,
                "pattern_type": "double_bottom",
                "break_time": pd.Timestamp(bars.iloc[break_idx]["timestamp"]).isoformat(),
                "follow_through_R": follow / pattern_height,
                "adverse_move_R": adverse / pattern_height,
                "reversal_win_flag": bool(follow > adverse),
            }
    return None


def compute_daily_metrics(
    bars: pd.DataFrame,
    atr_period: int,
    peak_tolerance_atr: float,
    min_pullback_atr: float,
    reversal_horizon_bars: int,
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
        if len(session) < 8:
            continue

        highs = _swing_highs(session)
        lows = _swing_lows(session)
        top = _detect_double_top(
            session,
            highs=highs,
            tol_atr=peak_tolerance_atr,
            min_pullback_atr=min_pullback_atr,
            horizon=reversal_horizon_bars,
        )
        bottom = _detect_double_bottom(
            session,
            lows=lows,
            tol_atr=peak_tolerance_atr,
            min_pullback_atr=min_pullback_atr,
            horizon=reversal_horizon_bars,
        )

        event = None
        if top is not None and bottom is not None:
            event = top if top["break_time"] <= bottom["break_time"] else bottom
        elif top is not None:
            event = top
        elif bottom is not None:
            event = bottom

        if event is None:
            rows.append(
                {
                    "date": date,
                    "pattern_flag": False,
                    "pattern_type": None,
                    "break_time": None,
                    "follow_through_R": pd.NA,
                    "adverse_move_R": pd.NA,
                    "reversal_win_flag": pd.NA,
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
    for metric in ["follow_through_R", "adverse_move_R"]:
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _safe_q(events[metric], q)})
    return pd.DataFrame(rows)


def build_summary(
    daily: pd.DataFrame,
    dataset_path: str,
    atr_period: int,
    peak_tolerance_atr: float,
    min_pullback_atr: float,
    reversal_horizon_bars: int,
) -> dict[str, object]:
    events = daily[daily["pattern_flag"]]
    bullish = events[events["pattern_type"] == "double_bottom"]
    bearish = events[events["pattern_type"] == "double_top"]
    wins = events["reversal_win_flag"].dropna()
    return {
        "dataset": dataset_path,
        "analysis_window_utc": {"start": ANALYSIS_START.strftime("%H:%M"), "end_exclusive": ANALYSIS_END.strftime("%H:%M")},
        "atr_period": atr_period,
        "peak_tolerance_atr": peak_tolerance_atr,
        "min_pullback_atr": min_pullback_atr,
        "reversal_horizon_bars": reversal_horizon_bars,
        "days_analyzed": int(len(daily)),
        "pattern_frequency": float(len(events) / len(daily)) if len(daily) else 0.0,
        "bullish_pattern_frequency": float(len(bullish) / len(events)) if len(events) else 0.0,
        "bearish_pattern_frequency": float(len(bearish) / len(events)) if len(events) else 0.0,
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
        atr_period=args.atr_period,
        peak_tolerance_atr=args.peak_tolerance_atr,
        min_pullback_atr=args.min_pullback_atr,
        reversal_horizon_bars=args.reversal_horizon_bars,
    )
    distribution = build_distribution(daily)
    summary = build_summary(
        daily,
        dataset_path=args.bars,
        atr_period=args.atr_period,
        peak_tolerance_atr=args.peak_tolerance_atr,
        min_pullback_atr=args.min_pullback_atr,
        reversal_horizon_bars=args.reversal_horizon_bars,
    )

    daily_path = out_dir / "daily_metrics.csv"
    dist_path = out_dir / "distribution.csv"
    summary_path = out_dir / "summary.json"
    daily.to_csv(daily_path, index=False)
    distribution.to_csv(dist_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"pattern_frequency: {summary['pattern_frequency']:.4f}")
    print(f"reversal_probability: {summary['reversal_probability']:.4f}")
    print(f"median_follow_through_R: {summary['median_follow_through_R']:.4f}")
    print(f"median_adverse_move_R: {summary['median_adverse_move_R']:.4f}")
    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
