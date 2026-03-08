from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add session labels and validate EURUSD 15m bars")
    parser.add_argument("--input-file", default="data/bars/15m/eurusd_bars_15m_2023_raw.parquet")
    parser.add_argument("--output-file", default="data/bars/15m/eurusd_bars_15m_2023.parquet")
    parser.add_argument("--report-file", default="data/bars/15m/eurusd_bars_15m_2023_report.json")
    return parser.parse_args()


def label_session(ts: pd.Timestamp) -> str:
    hour = ts.hour
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 13:
        return "london"
    return "new_york"


def continuity_report(df: pd.DataFrame) -> dict:
    ts = pd.to_datetime(df["timestamp"], utc=True)
    sorted_ok = bool(ts.is_monotonic_increasing)
    unique_ok = bool(~ts.duplicated().any())

    diffs = ts.diff().dropna()
    expected = pd.Timedelta(minutes=15)
    gap_count = int((diffs > expected).sum())
    irregular_step_count = int((diffs.dt.total_seconds() % (15 * 60) != 0).sum())

    return {
        "sorted": sorted_ok,
        "unique_timestamps": unique_ok,
        "gaps_gt_15m": gap_count,
        "irregular_step_count": irregular_step_count,
    }


def spread_stats(df: pd.DataFrame) -> dict:
    spread = df["spread_close"]
    return {
        "min": float(spread.min()),
        "p25": float(spread.quantile(0.25)),
        "median": float(spread.median()),
        "mean": float(spread.mean()),
        "p75": float(spread.quantile(0.75)),
        "p95": float(spread.quantile(0.95)),
        "p99": float(spread.quantile(0.99)),
        "max": float(spread.max()),
    }


def main() -> None:
    args = parse_args()
    input_file = Path(args.input_file)
    output_file = Path(args.output_file)
    report_file = Path(args.report_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.parent.mkdir(parents=True, exist_ok=True)

    bars = pd.read_parquet(input_file)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)
    bars["session_label"] = bars["timestamp"].map(label_session)

    continuity = continuity_report(bars)
    spread = spread_stats(bars)
    summary = {
        "rows": int(len(bars)),
        "start": bars["timestamp"].min().isoformat() if not bars.empty else None,
        "end": bars["timestamp"].max().isoformat() if not bars.empty else None,
        "continuity": continuity,
        "spread_stats": spread,
    }

    bars.to_parquet(output_file, index=False)
    report_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Saved final bars: {output_file}")
    print(f"Saved report: {report_file}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
