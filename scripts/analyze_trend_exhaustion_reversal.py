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
        description="Analyze trend exhaustion reversal behavior on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/trend_exhaustion_reversal_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    parser.add_argument("--atr-period", type=int, default=14, help="ATR period")
    parser.add_argument(
        "--impulse-atr-threshold",
        type=float,
        default=1.5,
        help="Impulse threshold in ATR multiples",
    )
    parser.add_argument(
        "--slowdown-factor",
        type=float,
        default=0.4,
        help="Next-bar body must be <= slowdown_factor * impulse_body",
    )
    parser.add_argument(
        "--structure-break-bars",
        type=int,
        default=4,
        help="Bars allowed to confirm opposite structure break",
    )
    parser.add_argument(
        "--reversal-horizon-bars",
        type=int,
        default=8,
        help="Bars for reversal/adverse move measurement after break",
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
    impulse_atr_threshold: float,
    slowdown_factor: float,
    structure_break_bars: int,
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
        if len(session) < 6:
            continue

        event = None
        for i in range(len(session) - 2):
            atr = float(session.iloc[i]["atr"]) if pd.notna(session.iloc[i]["atr"]) else 0.0
            if atr <= 0:
                continue
            impulse_body = abs(float(session.iloc[i]["mid_close"]) - float(session.iloc[i]["mid_open"]))
            if impulse_body < impulse_atr_threshold * atr:
                continue

            next_body = abs(float(session.iloc[i + 1]["mid_close"]) - float(session.iloc[i + 1]["mid_open"]))
            if next_body > slowdown_factor * impulse_body:
                continue

            direction = "bullish" if float(session.iloc[i]["mid_close"]) > float(session.iloc[i]["mid_open"]) else "bearish"
            low_i = float(session.iloc[i]["mid_low"])
            high_i = float(session.iloc[i]["mid_high"])
            break_idx = None
            upper = min(i + 1 + structure_break_bars, len(session))
            for j in range(i + 1, upper):
                close_j = float(session.iloc[j]["mid_close"])
                if direction == "bullish" and close_j < low_i:
                    break_idx = j
                    break
                if direction == "bearish" and close_j > high_i:
                    break_idx = j
                    break
            if break_idx is None:
                continue

            break_close = float(session.iloc[break_idx]["mid_close"])
            horizon = session.iloc[break_idx + 1 : break_idx + 1 + reversal_horizon_bars]
            if horizon.empty:
                continue
            if direction == "bullish":
                reversal = max(0.0, break_close - float(horizon["mid_low"].min()))
                adverse = max(0.0, float(horizon["mid_high"].max()) - break_close)
            else:
                reversal = max(0.0, float(horizon["mid_high"].max()) - break_close)
                adverse = max(0.0, break_close - float(horizon["mid_low"].min()))

            event = {
                "exhaustion_event_flag": True,
                "exhaustion_direction": direction,
                "impulse_time": pd.Timestamp(session.iloc[i]["timestamp"]).isoformat(),
                "break_time": pd.Timestamp(session.iloc[break_idx]["timestamp"]).isoformat(),
                "reversal_ratio": reversal / impulse_body if impulse_body > 0 else pd.NA,
                "adverse_move_ratio": adverse / impulse_body if impulse_body > 0 else pd.NA,
                "reversal_win_flag": bool(reversal > adverse),
            }
            break

        if event is None:
            rows.append(
                {
                    "date": date,
                    "exhaustion_event_flag": False,
                    "exhaustion_direction": None,
                    "impulse_time": None,
                    "break_time": None,
                    "reversal_ratio": pd.NA,
                    "adverse_move_ratio": pd.NA,
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
    events = daily[daily["exhaustion_event_flag"]]
    rows: list[dict[str, object]] = []
    for metric in ["reversal_ratio", "adverse_move_ratio"]:
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _safe_q(events[metric], q)})
    return pd.DataFrame(rows)


def build_summary(
    daily: pd.DataFrame,
    dataset_path: str,
    atr_period: int,
    impulse_atr_threshold: float,
    slowdown_factor: float,
    structure_break_bars: int,
    reversal_horizon_bars: int,
) -> dict[str, object]:
    events = daily[daily["exhaustion_event_flag"]]
    wins = events["reversal_win_flag"].dropna()
    return {
        "dataset": dataset_path,
        "analysis_window_utc": {"start": ANALYSIS_START.strftime("%H:%M"), "end_exclusive": ANALYSIS_END.strftime("%H:%M")},
        "atr_period": atr_period,
        "impulse_atr_threshold": impulse_atr_threshold,
        "slowdown_factor": slowdown_factor,
        "structure_break_bars": structure_break_bars,
        "reversal_horizon_bars": reversal_horizon_bars,
        "days_analyzed": int(len(daily)),
        "exhaustion_event_frequency": float(len(events) / len(daily)) if len(daily) else 0.0,
        "reversal_probability": float(wins.mean()) if len(wins) else 0.0,
        "median_reversal_ratio": _safe_q(events["reversal_ratio"], 0.50),
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
        impulse_atr_threshold=args.impulse_atr_threshold,
        slowdown_factor=args.slowdown_factor,
        structure_break_bars=args.structure_break_bars,
        reversal_horizon_bars=args.reversal_horizon_bars,
    )
    distribution = build_distribution(daily)
    summary = build_summary(
        daily,
        dataset_path=args.bars,
        atr_period=args.atr_period,
        impulse_atr_threshold=args.impulse_atr_threshold,
        slowdown_factor=args.slowdown_factor,
        structure_break_bars=args.structure_break_bars,
        reversal_horizon_bars=args.reversal_horizon_bars,
    )

    daily_path = out_dir / "daily_metrics.csv"
    dist_path = out_dir / "distribution.csv"
    summary_path = out_dir / "summary.json"
    daily.to_csv(daily_path, index=False)
    distribution.to_csv(dist_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"exhaustion_event_frequency: {summary['exhaustion_event_frequency']:.4f}")
    print(f"reversal_probability: {summary['reversal_probability']:.4f}")
    print(f"median_reversal_ratio: {summary['median_reversal_ratio']:.4f}")
    print(f"median_adverse_move_ratio: {summary['median_adverse_move_ratio']:.4f}")
    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
