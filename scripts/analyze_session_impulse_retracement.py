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


SESSIONS = {
    "london": {
        "impulse_start": time(8, 0),
        "impulse_end": time(8, 30),
        "retracement_start": time(8, 30),
        "retracement_end": time(10, 0),
    },
    "ny": {
        "impulse_start": time(13, 0),
        "impulse_end": time(13, 30),
        "retracement_start": time(13, 30),
        "retracement_end": time(15, 0),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze London and New York opening impulse retracement behavior."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Path to EURUSD M15 bars parquet",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/session_impulse_retracement",
        help="Directory for daily_metrics.csv and summary.json",
    )
    return parser.parse_args()


def _window_mask(series: pd.Series, start: time, end: time) -> pd.Series:
    if start <= end:
        return (series >= start) & (series < end)
    return (series >= start) | (series < end)


def compute_daily_metrics(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time

    all_rows: list[dict] = []

    for session_name, cfg in SESSIONS.items():
        impulse_mask = _window_mask(df["tod"], cfg["impulse_start"], cfg["impulse_end"])
        retracement_mask = _window_mask(
            df["tod"], cfg["retracement_start"], cfg["retracement_end"]
        )

        impulse = df.loc[impulse_mask, ["date", "mid_high", "mid_low"]].copy()
        retracement = df.loc[retracement_mask, ["date", "mid_high", "mid_low"]].copy()

        impulse_daily = (
            impulse.groupby("date")
            .agg(impulse_high=("mid_high", "max"), impulse_low=("mid_low", "min"))
            .reset_index()
        )
        impulse_daily["impulse_size"] = impulse_daily["impulse_high"] - impulse_daily["impulse_low"]

        retr_daily = (
            retracement.groupby("date")
            .agg(retracement_high=("mid_high", "max"), retracement_low=("mid_low", "min"))
            .reset_index()
        )

        merged = impulse_daily.merge(retr_daily, on="date", how="inner")
        merged = merged[merged["impulse_size"] > 0.0].copy()
        if merged.empty:
            continue

        merged["retracement_size_long"] = (
            merged["impulse_high"] - merged["retracement_low"]
        )
        merged["retracement_size_short"] = (
            merged["retracement_high"] - merged["impulse_low"]
        )
        merged["retracement_ratio"] = merged[
            ["retracement_size_long", "retracement_size_short"]
        ].max(axis=1) / merged["impulse_size"]

        for _, row in merged.iterrows():
            all_rows.append(
                {
                    "date": row["date"],
                    "session": session_name,
                    "impulse_size": float(row["impulse_size"]),
                    "retracement_size_long": float(row["retracement_size_long"]),
                    "retracement_size_short": float(row["retracement_size_short"]),
                    "retracement_ratio": float(row["retracement_ratio"]),
                }
            )

    out = pd.DataFrame(all_rows)
    if out.empty:
        raise ValueError("No daily session metrics could be computed from input bars")
    return out.sort_values(["date", "session"]).reset_index(drop=True)


def _quantile_table(series: pd.Series) -> dict[str, float]:
    return {
        "p10": float(series.quantile(0.10)),
        "p25": float(series.quantile(0.25)),
        "p50": float(series.quantile(0.50)),
        "p75": float(series.quantile(0.75)),
        "p90": float(series.quantile(0.90)),
    }


def build_summary(daily: pd.DataFrame, dataset_path: str) -> dict:
    sessions_summary: dict[str, dict] = {}
    segment_rows: list[dict] = []

    for session_name, session_df in daily.groupby("session"):
        impulse_quantiles = _quantile_table(session_df["impulse_size"])
        retracement_quantiles = _quantile_table(session_df["retracement_ratio"])

        segments = []
        for q in ("p50", "p75", "p90"):
            threshold = impulse_quantiles[q]
            subset = session_df[session_df["impulse_size"] >= threshold]
            avg_ratio = float(subset["retracement_ratio"].mean()) if not subset.empty else 0.0
            median_ratio = (
                float(subset["retracement_ratio"].median()) if not subset.empty else 0.0
            )
            samples = int(len(subset))
            row = {
                "session": session_name,
                "impulse_quantile": q,
                "impulse_threshold": float(threshold),
                "avg_retracement_ratio": avg_ratio,
                "median_retracement_ratio": median_ratio,
                "samples": samples,
            }
            segments.append(row)
            segment_rows.append(row)

        sessions_summary[session_name] = {
            "days_analyzed": int(len(session_df)),
            "impulse_size_quantiles": impulse_quantiles,
            "retracement_ratio_quantiles": retracement_quantiles,
            "impulse_quantile_segments": segments,
        }

    return {
        "dataset": dataset_path,
        "sessions": sessions_summary,
        "total_rows": int(len(daily)),
        "segment_table": segment_rows,
    }


def print_segment_table(segment_rows: list[dict]) -> None:
    print("session | impulse_quantile | avg_retracement_ratio | median_retracement_ratio | samples")
    for row in segment_rows:
        print(
            f"{row['session']:>7} | {row['impulse_quantile']:>15} | "
            f"{row['avg_retracement_ratio']:>21.6f} | "
            f"{row['median_retracement_ratio']:>24.6f} | "
            f"{row['samples']:>7}"
        )


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars)
    daily = compute_daily_metrics(bars)

    daily_path = out_dir / "daily_metrics.csv"
    summary_path = out_dir / "summary.json"
    daily.to_csv(daily_path, index=False)

    summary = build_summary(daily, dataset_path=args.bars)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print_segment_table(summary["segment_table"])
    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
