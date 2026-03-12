from __future__ import annotations

import argparse
import json
import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.data.loaders import load_bars


SESSIONS = {
    "london": (time(7, 0), time(12, 0)),
    "ny": (time(12, 0), time(17, 0)),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze session VWAP reversion behavior on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/session_vwap_reversion_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    parser.add_argument(
        "--atr-period",
        type=int,
        default=14,
        help="ATR period for deviation normalization",
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


def compute_observations(bars: pd.DataFrame, atr_period: int) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["atr"] = _compute_atr(df, period=atr_period)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time
    df["typical_price"] = (df["mid_high"] + df["mid_low"] + df["mid_close"]) / 3.0

    rows: list[dict[str, object]] = []

    for date, day in df.groupby("date", sort=True):
        for session_name, (start, end) in SESSIONS.items():
            session = day.loc[_window_mask(day["tod"], start, end)].copy().reset_index(drop=True)
            if session.empty:
                continue

            session["session_vwap"] = session["typical_price"].expanding().mean()
            session["deviation"] = session["mid_close"] - session["session_vwap"]

            for i, row in session.iterrows():
                atr = float(row["atr"]) if pd.notna(row["atr"]) else np.nan
                if np.isnan(atr) or atr <= 0:
                    continue
                deviation = float(row["deviation"])
                abs_dev = abs(deviation)
                if abs_dev == 0:
                    continue

                r4 = pd.NA
                r8 = pd.NA
                j4 = i + 4
                j8 = i + 8
                if j4 < len(session):
                    abs_dev_4 = abs(float(session.iloc[j4]["deviation"]))
                    r4 = (abs_dev - abs_dev_4) / abs_dev
                if j8 < len(session):
                    abs_dev_8 = abs(float(session.iloc[j8]["deviation"]))
                    r8 = (abs_dev - abs_dev_8) / abs_dev

                rows.append(
                    {
                        "date": date,
                        "timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
                        "session": session_name,
                        "deviation": deviation,
                        "deviation_atr": deviation / atr,
                        "abs_deviation_atr": abs(deviation / atr),
                        "reversion_ratio_4bars": r4,
                        "reversion_ratio_8bars": r8,
                    }
                )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("No observations produced from dataset")
    return out


def assign_buckets(observations: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    out = observations.copy()
    p50 = _safe_q(out["abs_deviation_atr"], 0.50)
    p75 = _safe_q(out["abs_deviation_atr"], 0.75)
    p90 = _safe_q(out["abs_deviation_atr"], 0.90)

    def label(x: float) -> str:
        if x <= p50:
            return "small_dev"
        if x <= p75:
            return "medium_dev"
        if x <= p90:
            return "large_dev"
        return "extreme_dev"

    out["deviation_bucket"] = out["abs_deviation_atr"].apply(label)
    return out, {"p50": p50, "p75": p75, "p90": p90}


def _bucket_stats(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for bucket, part in df.groupby("deviation_bucket"):
        result[bucket] = {
            "count": float(len(part)),
            "median_reversion_ratio_4bars": _safe_q(part["reversion_ratio_4bars"], 0.50),
            "median_reversion_ratio_8bars": _safe_q(part["reversion_ratio_8bars"], 0.50),
        }
    return result


def build_distribution(observations: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metric in ["abs_deviation_atr", "reversion_ratio_4bars", "reversion_ratio_8bars"]:
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _safe_q(observations[metric], q)})
    return pd.DataFrame(rows)


def build_summary(
    observations: pd.DataFrame,
    dataset_path: str,
    atr_period: int,
    bucket_cutoffs: dict[str, float],
) -> dict[str, object]:
    london = observations[observations["session"] == "london"]
    ny = observations[observations["session"] == "ny"]
    pos = observations[observations["deviation"] > 0]
    neg = observations[observations["deviation"] < 0]

    return {
        "dataset": dataset_path,
        "sessions_utc": {
            "london": {"start": SESSIONS["london"][0].strftime("%H:%M"), "end_exclusive": SESSIONS["london"][1].strftime("%H:%M")},
            "ny": {"start": SESSIONS["ny"][0].strftime("%H:%M"), "end_exclusive": SESSIONS["ny"][1].strftime("%H:%M")},
        },
        "atr_period": atr_period,
        "bars_analyzed": int(len(observations)),
        "median_abs_deviation_atr": _safe_q(observations["abs_deviation_atr"], 0.50),
        "p75_abs_deviation_atr": _safe_q(observations["abs_deviation_atr"], 0.75),
        "p90_abs_deviation_atr": _safe_q(observations["abs_deviation_atr"], 0.90),
        "median_reversion_ratio_4bars": _safe_q(observations["reversion_ratio_4bars"], 0.50),
        "median_reversion_ratio_8bars": _safe_q(observations["reversion_ratio_8bars"], 0.50),
        "deviation_bucket_cutoffs": bucket_cutoffs,
        "deviation_bucket_stats": _bucket_stats(observations),
        "session_stats": {
            "london": {
                "count": int(len(london)),
                "median_reversion_ratio_4bars": _safe_q(london["reversion_ratio_4bars"], 0.50),
                "median_reversion_ratio_8bars": _safe_q(london["reversion_ratio_8bars"], 0.50),
            },
            "ny": {
                "count": int(len(ny)),
                "median_reversion_ratio_4bars": _safe_q(ny["reversion_ratio_4bars"], 0.50),
                "median_reversion_ratio_8bars": _safe_q(ny["reversion_ratio_8bars"], 0.50),
            },
        },
        "positive_deviation_stats": {
            "count": int(len(pos)),
            "median_reversion_ratio_4bars": _safe_q(pos["reversion_ratio_4bars"], 0.50),
            "median_reversion_ratio_8bars": _safe_q(pos["reversion_ratio_8bars"], 0.50),
        },
        "negative_deviation_stats": {
            "count": int(len(neg)),
            "median_reversion_ratio_4bars": _safe_q(neg["reversion_ratio_4bars"], 0.50),
            "median_reversion_ratio_8bars": _safe_q(neg["reversion_ratio_8bars"], 0.50),
        },
    }


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars)
    observations = compute_observations(bars, atr_period=args.atr_period)
    observations, bucket_cutoffs = assign_buckets(observations)
    distribution = build_distribution(observations)
    summary = build_summary(
        observations,
        dataset_path=args.bars,
        atr_period=args.atr_period,
        bucket_cutoffs=bucket_cutoffs,
    )

    obs_path = out_dir / "daily_metrics.csv"
    dist_path = out_dir / "distribution.csv"
    summary_path = out_dir / "summary.json"
    observations.to_csv(obs_path, index=False)
    distribution.to_csv(dist_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"bars_analyzed: {summary['bars_analyzed']}")
    print(f"median_abs_deviation_atr: {summary['median_abs_deviation_atr']:.4f}")
    print(f"median_reversion_ratio_4bars: {summary['median_reversion_ratio_4bars']:.4f}")
    print(f"median_reversion_ratio_8bars: {summary['median_reversion_ratio_8bars']:.4f}")
    print(f"\nSaved daily metrics: {obs_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
