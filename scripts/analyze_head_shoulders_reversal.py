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
        description="Analyze head-and-shoulders reversal behavior on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/head_shoulders_reversal_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    parser.add_argument("--atr-period", type=int, default=14, help="ATR period")
    parser.add_argument(
        "--shoulder-tolerance-atr",
        type=float,
        default=0.3,
        help="Shoulders must be within this ATR multiple",
    )
    parser.add_argument(
        "--min-head-lift-atr",
        type=float,
        default=0.3,
        help="Head must exceed shoulders by at least this ATR multiple",
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


def _detect_head_shoulders(
    bars: pd.DataFrame,
    highs: list[int],
    shoulder_tolerance_atr: float,
    min_head_lift_atr: float,
    reversal_horizon_bars: int,
) -> dict[str, object] | None:
    for i in range(len(highs) - 2):
        ls_idx = highs[i]
        for j in range(i + 1, len(highs) - 1):
            head_idx = highs[j]
            if head_idx - ls_idx < 2:
                continue
            for k in range(j + 1, len(highs)):
                rs_idx = highs[k]
                if rs_idx - head_idx < 2:
                    continue

                ls = float(bars.iloc[ls_idx]["mid_high"])
                head = float(bars.iloc[head_idx]["mid_high"])
                rs = float(bars.iloc[rs_idx]["mid_high"])
                atr = float(bars.iloc[head_idx]["atr"]) if pd.notna(bars.iloc[head_idx]["atr"]) else 0.0
                if atr <= 0:
                    continue
                if head <= max(ls, rs):
                    continue
                if (head - max(ls, rs)) < min_head_lift_atr * atr:
                    continue
                if abs(ls - rs) > shoulder_tolerance_atr * atr:
                    continue

                left_neck = float(bars.iloc[ls_idx + 1 : head_idx]["mid_low"].min())
                right_neck = float(bars.iloc[head_idx + 1 : rs_idx]["mid_low"].min())
                if pd.isna(left_neck) or pd.isna(right_neck):
                    continue
                neckline = (left_neck + right_neck) / 2.0

                break_idx: int | None = None
                for b in range(rs_idx + 1, len(bars)):
                    if float(bars.iloc[b]["mid_close"]) < neckline:
                        break_idx = b
                        break
                if break_idx is None:
                    continue

                pattern_height = head - neckline
                if pattern_height <= 0:
                    continue
                post = bars.iloc[break_idx + 1 : break_idx + 1 + reversal_horizon_bars]
                if post.empty:
                    continue

                follow = max(0.0, neckline - float(post["mid_low"].min()))
                adverse = max(0.0, float(post["mid_high"].max()) - neckline)
                return {
                    "pattern_flag": True,
                    "pattern_type": "head_shoulders",
                    "break_time": pd.Timestamp(bars.iloc[break_idx]["timestamp"]).isoformat(),
                    "follow_through_R": follow / pattern_height,
                    "adverse_move_R": adverse / pattern_height,
                    "reversal_win_flag": bool(follow > adverse),
                }
    return None


def _detect_inverse_head_shoulders(
    bars: pd.DataFrame,
    lows: list[int],
    shoulder_tolerance_atr: float,
    min_head_lift_atr: float,
    reversal_horizon_bars: int,
) -> dict[str, object] | None:
    for i in range(len(lows) - 2):
        ls_idx = lows[i]
        for j in range(i + 1, len(lows) - 1):
            head_idx = lows[j]
            if head_idx - ls_idx < 2:
                continue
            for k in range(j + 1, len(lows)):
                rs_idx = lows[k]
                if rs_idx - head_idx < 2:
                    continue

                ls = float(bars.iloc[ls_idx]["mid_low"])
                head = float(bars.iloc[head_idx]["mid_low"])
                rs = float(bars.iloc[rs_idx]["mid_low"])
                atr = float(bars.iloc[head_idx]["atr"]) if pd.notna(bars.iloc[head_idx]["atr"]) else 0.0
                if atr <= 0:
                    continue
                if head >= min(ls, rs):
                    continue
                if (min(ls, rs) - head) < min_head_lift_atr * atr:
                    continue
                if abs(ls - rs) > shoulder_tolerance_atr * atr:
                    continue

                left_neck = float(bars.iloc[ls_idx + 1 : head_idx]["mid_high"].max())
                right_neck = float(bars.iloc[head_idx + 1 : rs_idx]["mid_high"].max())
                if pd.isna(left_neck) or pd.isna(right_neck):
                    continue
                neckline = (left_neck + right_neck) / 2.0

                break_idx: int | None = None
                for b in range(rs_idx + 1, len(bars)):
                    if float(bars.iloc[b]["mid_close"]) > neckline:
                        break_idx = b
                        break
                if break_idx is None:
                    continue

                pattern_height = neckline - head
                if pattern_height <= 0:
                    continue
                post = bars.iloc[break_idx + 1 : break_idx + 1 + reversal_horizon_bars]
                if post.empty:
                    continue

                follow = max(0.0, float(post["mid_high"].max()) - neckline)
                adverse = max(0.0, neckline - float(post["mid_low"].min()))
                return {
                    "pattern_flag": True,
                    "pattern_type": "inverse_head_shoulders",
                    "break_time": pd.Timestamp(bars.iloc[break_idx]["timestamp"]).isoformat(),
                    "follow_through_R": follow / pattern_height,
                    "adverse_move_R": adverse / pattern_height,
                    "reversal_win_flag": bool(follow > adverse),
                }
    return None


def compute_daily_metrics(
    bars: pd.DataFrame,
    atr_period: int,
    shoulder_tolerance_atr: float,
    min_head_lift_atr: float,
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
        if len(session) < 10:
            continue

        hs = _detect_head_shoulders(
            session,
            highs=_swing_highs(session),
            shoulder_tolerance_atr=shoulder_tolerance_atr,
            min_head_lift_atr=min_head_lift_atr,
            reversal_horizon_bars=reversal_horizon_bars,
        )
        ihs = _detect_inverse_head_shoulders(
            session,
            lows=_swing_lows(session),
            shoulder_tolerance_atr=shoulder_tolerance_atr,
            min_head_lift_atr=min_head_lift_atr,
            reversal_horizon_bars=reversal_horizon_bars,
        )

        event = None
        if hs is not None and ihs is not None:
            event = hs if hs["break_time"] <= ihs["break_time"] else ihs
        elif hs is not None:
            event = hs
        elif ihs is not None:
            event = ihs

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
    shoulder_tolerance_atr: float,
    min_head_lift_atr: float,
    reversal_horizon_bars: int,
) -> dict[str, object]:
    events = daily[daily["pattern_flag"]]
    wins = events["reversal_win_flag"].dropna()
    bearish = events["pattern_type"] == "head_shoulders"
    bullish = events["pattern_type"] == "inverse_head_shoulders"
    return {
        "dataset": dataset_path,
        "analysis_window_utc": {"start": ANALYSIS_START.strftime("%H:%M"), "end_exclusive": ANALYSIS_END.strftime("%H:%M")},
        "atr_period": atr_period,
        "shoulder_tolerance_atr": shoulder_tolerance_atr,
        "min_head_lift_atr": min_head_lift_atr,
        "reversal_horizon_bars": reversal_horizon_bars,
        "days_analyzed": int(len(daily)),
        "pattern_frequency": float(len(events) / len(daily)) if len(daily) else 0.0,
        "bearish_pattern_frequency": float(bearish.sum() / len(daily)) if len(daily) else 0.0,
        "bullish_pattern_frequency": float(bullish.sum() / len(daily)) if len(daily) else 0.0,
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
        shoulder_tolerance_atr=args.shoulder_tolerance_atr,
        min_head_lift_atr=args.min_head_lift_atr,
        reversal_horizon_bars=args.reversal_horizon_bars,
    )
    distribution = build_distribution(daily)
    summary = build_summary(
        daily,
        dataset_path=args.bars,
        atr_period=args.atr_period,
        shoulder_tolerance_atr=args.shoulder_tolerance_atr,
        min_head_lift_atr=args.min_head_lift_atr,
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
