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
        "reversal_start": time(8, 30),
        "reversal_end": time(10, 0),
    },
    "ny": {
        "impulse_start": time(13, 0),
        "impulse_end": time(13, 30),
        "reversal_start": time(13, 30),
        "reversal_end": time(15, 0),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze directional reversal after London/NY opening impulses."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Path to EURUSD M15 bars parquet",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/session_impulse_reversal",
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

    rows: list[dict] = []
    for session_name, cfg in SESSIONS.items():
        impulse_mask = _window_mask(df["tod"], cfg["impulse_start"], cfg["impulse_end"])
        reversal_mask = _window_mask(df["tod"], cfg["reversal_start"], cfg["reversal_end"])

        impulse = df.loc[
            impulse_mask, ["date", "timestamp", "mid_open", "mid_high", "mid_low", "mid_close"]
        ].copy()
        reversal = df.loc[reversal_mask, ["date", "mid_high", "mid_low"]].copy()

        if impulse.empty or reversal.empty:
            continue

        impulse_daily = (
            impulse.groupby("date")
            .agg(
                impulse_high=("mid_high", "max"),
                impulse_low=("mid_low", "min"),
                impulse_open=("mid_open", "first"),
                impulse_close=("mid_close", "last"),
            )
            .reset_index()
        )
        impulse_daily["impulse_size"] = impulse_daily["impulse_high"] - impulse_daily["impulse_low"]

        reversal_daily = (
            reversal.groupby("date")
            .agg(reversal_high=("mid_high", "max"), reversal_low=("mid_low", "min"))
            .reset_index()
        )

        merged = impulse_daily.merge(reversal_daily, on="date", how="inner")
        merged = merged[merged["impulse_size"] > 0.0].copy()
        if merged.empty:
            continue

        merged["impulse_direction"] = 0
        merged.loc[merged["impulse_close"] > merged["impulse_open"], "impulse_direction"] = 1
        merged.loc[merged["impulse_close"] < merged["impulse_open"], "impulse_direction"] = -1

        up_mask = merged["impulse_direction"] == 1
        down_mask = merged["impulse_direction"] == -1

        merged["reversal"] = pd.NA
        merged.loc[up_mask, "reversal"] = (
            merged.loc[up_mask, "impulse_high"] - merged.loc[up_mask, "reversal_low"]
        )
        merged.loc[down_mask, "reversal"] = (
            merged.loc[down_mask, "reversal_high"] - merged.loc[down_mask, "impulse_low"]
        )

        merged["reversal_ratio"] = merged["reversal"] / merged["impulse_size"]
        merged = merged[merged["impulse_direction"] != 0].copy()
        if merged.empty:
            continue

        for _, row in merged.iterrows():
            rows.append(
                {
                    "date": row["date"],
                    "session": session_name,
                    "impulse_size": float(row["impulse_size"]),
                    "impulse_direction": int(row["impulse_direction"]),
                    "reversal": float(row["reversal"]),
                    "reversal_ratio": float(row["reversal_ratio"]),
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("No directional impulse/reversal rows were computed")
    return out.sort_values(["date", "session"]).reset_index(drop=True)


def _quantiles(series: pd.Series) -> dict[str, float]:
    return {
        "p10": float(series.quantile(0.10)),
        "p25": float(series.quantile(0.25)),
        "p50": float(series.quantile(0.50)),
        "p75": float(series.quantile(0.75)),
        "p90": float(series.quantile(0.90)),
    }


def build_summary(daily: pd.DataFrame, dataset_path: str) -> dict:
    sessions: dict[str, dict] = {}
    segment_rows: list[dict] = []

    for session_name, session_df in daily.groupby("session"):
        impulse_q = _quantiles(session_df["impulse_size"])
        reversal_q = _quantiles(session_df["reversal_ratio"])

        segments = []
        for q in ("p50", "p75", "p90"):
            threshold = impulse_q[q]
            subset = session_df[session_df["impulse_size"] >= threshold]
            row = {
                "session": session_name,
                "impulse_quantile": q,
                "impulse_threshold": float(threshold),
                "avg_reversal_ratio": float(subset["reversal_ratio"].mean()) if not subset.empty else 0.0,
                "median_reversal_ratio": float(subset["reversal_ratio"].median()) if not subset.empty else 0.0,
                "samples": int(len(subset)),
            }
            segments.append(row)
            segment_rows.append(row)

        sessions[session_name] = {
            "days_analyzed": int(len(session_df)),
            "impulse_size_quantiles": impulse_q,
            "reversal_ratio_quantiles": reversal_q,
            "impulse_quantile_segments": segments,
        }

    return {
        "dataset": dataset_path,
        "sessions": sessions,
        "total_rows": int(len(daily)),
        "segment_table": segment_rows,
    }


def print_table(segment_rows: list[dict]) -> None:
    print("session | impulse_quantile | avg_reversal_ratio | median_reversal_ratio | samples")
    for row in segment_rows:
        print(
            f"{row['session']:>7} | {row['impulse_quantile']:>15} | "
            f"{row['avg_reversal_ratio']:>18.6f} | "
            f"{row['median_reversal_ratio']:>21.6f} | "
            f"{row['samples']:>7}"
        )


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars)
    daily = compute_daily_metrics(bars)
    daily = daily[
        ["date", "session", "impulse_size", "impulse_direction", "reversal", "reversal_ratio"]
    ]

    daily_path = out_dir / "daily_metrics.csv"
    summary_path = out_dir / "summary.json"
    daily.to_csv(daily_path, index=False)

    summary = build_summary(daily, dataset_path=args.bars)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print_table(summary["segment_table"])
    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
