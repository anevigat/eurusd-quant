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


SESSION_START = time(13, 0)
SESSION_END = time(16, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze double impulse exhaustion behavior on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/double_impulse_exhaustion_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    parser.add_argument(
        "--atr-period",
        type=int,
        default=14,
        help="ATR period for impulse normalization",
    )
    parser.add_argument(
        "--impulse-atr-multiple",
        type=float,
        default=0.8,
        help="Impulse threshold as abs(bar close-open) >= multiple * ATR",
    )
    parser.add_argument(
        "--max-gap-bars",
        type=int,
        default=8,
        help="Maximum bar gap between first and second impulse",
    )
    parser.add_argument(
        "--reversal-horizon-bars",
        type=int,
        default=8,
        help="Bars to measure reversal after second impulse",
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


def compute_daily_metrics(
    bars: pd.DataFrame,
    atr_period: int,
    impulse_atr_multiple: float,
    max_gap_bars: int,
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
        session = day.loc[_window_mask(day["tod"], SESSION_START, SESSION_END)].reset_index(drop=True)
        if session.empty:
            continue

        impulses: list[dict[str, float | int | str]] = []
        for idx, row in session.iterrows():
            atr = float(row["atr"]) if pd.notna(row["atr"]) else 0.0
            if atr <= 0:
                continue
            bar_move = float(row["mid_close"]) - float(row["mid_open"])
            impulse_size = abs(bar_move)
            if impulse_size >= impulse_atr_multiple * atr:
                impulses.append(
                    {
                        "idx": idx,
                        "direction": "bullish" if bar_move > 0 else "bearish",
                        "impulse_size": impulse_size,
                        "close": float(row["mid_close"]),
                        "timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
                    }
                )

        double_flag = False
        double_direction: str | None = None
        first_impulse_time: str | None = None
        second_impulse_time: str | None = None
        reversal_ratio = pd.NA
        adverse_move_ratio = pd.NA
        reversal_win_flag = pd.NA

        if len(impulses) >= 2:
            first_idx = None
            second_idx = None
            for i in range(len(impulses) - 1):
                for j in range(i + 1, len(impulses)):
                    if impulses[i]["direction"] != impulses[j]["direction"]:
                        continue
                    if int(impulses[j]["idx"]) - int(impulses[i]["idx"]) > max_gap_bars:
                        continue
                    first_idx = i
                    second_idx = j
                    break
                if second_idx is not None:
                    break

            if first_idx is not None and second_idx is not None:
                first = impulses[first_idx]
                second = impulses[second_idx]
                double_flag = True
                double_direction = str(second["direction"])
                first_impulse_time = str(first["timestamp"])
                second_impulse_time = str(second["timestamp"])
                second_bar_idx = int(second["idx"])
                entry = float(second["close"])
                second_size = float(second["impulse_size"])
                horizon = session.iloc[
                    second_bar_idx + 1 : second_bar_idx + 1 + reversal_horizon_bars
                ]
                if not horizon.empty and second_size > 0:
                    if double_direction == "bullish":
                        reversal = max(0.0, entry - float(horizon["mid_low"].min()))
                        adverse = max(0.0, float(horizon["mid_high"].max()) - entry)
                    else:
                        reversal = max(0.0, float(horizon["mid_high"].max()) - entry)
                        adverse = max(0.0, entry - float(horizon["mid_low"].min()))
                    reversal_ratio = reversal / second_size
                    adverse_move_ratio = adverse / second_size
                    reversal_win_flag = bool(reversal > adverse)

        rows.append(
            {
                "date": date,
                "double_impulse_flag": double_flag,
                "double_impulse_direction": double_direction,
                "first_impulse_time": first_impulse_time,
                "second_impulse_time": second_impulse_time,
                "reversal_ratio": reversal_ratio,
                "adverse_move_ratio": adverse_move_ratio,
                "reversal_win_flag": reversal_win_flag,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("No daily rows produced from dataset")
    return out


def build_distribution(daily: pd.DataFrame) -> pd.DataFrame:
    events = daily[daily["double_impulse_flag"]]
    rows: list[dict[str, object]] = []
    for metric in ["reversal_ratio", "adverse_move_ratio"]:
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _safe_q(events[metric], q)})
    return pd.DataFrame(rows)


def build_summary(
    daily: pd.DataFrame,
    dataset_path: str,
    atr_period: int,
    impulse_atr_multiple: float,
    max_gap_bars: int,
    reversal_horizon_bars: int,
) -> dict[str, object]:
    events = daily[daily["double_impulse_flag"]]
    bull = events[events["double_impulse_direction"] == "bullish"]
    bear = events[events["double_impulse_direction"] == "bearish"]
    wins = events["reversal_win_flag"].dropna()

    return {
        "dataset": dataset_path,
        "session_window_utc": {"start": SESSION_START.strftime("%H:%M"), "end_exclusive": SESSION_END.strftime("%H:%M")},
        "atr_period": atr_period,
        "impulse_atr_multiple": impulse_atr_multiple,
        "max_gap_bars": max_gap_bars,
        "reversal_horizon_bars": reversal_horizon_bars,
        "days_analyzed": int(len(daily)),
        "double_impulse_frequency": float(len(events) / len(daily)) if len(daily) else 0.0,
        "bullish_double_impulse_frequency": float(len(bull) / len(events)) if len(events) else 0.0,
        "bearish_double_impulse_frequency": float(len(bear) / len(events)) if len(events) else 0.0,
        "reversal_probability": float(wins.mean()) if len(wins) else 0.0,
        "median_reversal_ratio": _safe_q(events["reversal_ratio"], 0.50),
        "p75_reversal_ratio": _safe_q(events["reversal_ratio"], 0.75),
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
        impulse_atr_multiple=args.impulse_atr_multiple,
        max_gap_bars=args.max_gap_bars,
        reversal_horizon_bars=args.reversal_horizon_bars,
    )
    distribution = build_distribution(daily)
    summary = build_summary(
        daily,
        dataset_path=args.bars,
        atr_period=args.atr_period,
        impulse_atr_multiple=args.impulse_atr_multiple,
        max_gap_bars=args.max_gap_bars,
        reversal_horizon_bars=args.reversal_horizon_bars,
    )

    daily_path = out_dir / "daily_metrics.csv"
    dist_path = out_dir / "distribution.csv"
    summary_path = out_dir / "summary.json"
    daily.to_csv(daily_path, index=False)
    distribution.to_csv(dist_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"double_impulse_frequency: {summary['double_impulse_frequency']:.4f}")
    print(f"reversal_probability: {summary['reversal_probability']:.4f}")
    print(f"median_reversal_ratio: {summary['median_reversal_ratio']:.4f}")
    print(f"median_adverse_move_ratio: {summary['median_adverse_move_ratio']:.4f}")
    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
