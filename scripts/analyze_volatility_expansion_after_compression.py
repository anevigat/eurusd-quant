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


SESSION_WINDOWS = {
    "asia": (time(0, 0), time(7, 0)),
    "london": (time(7, 0), time(13, 0)),
    "ny": (time(13, 0), time(21, 0)),
}
SESSION_ORDER = ["asia", "london", "ny"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze volatility expansion after compressed sessions on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/volatility_expansion_after_compression_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    parser.add_argument(
        "--compression-quantile",
        type=float,
        default=0.25,
        help="Quantile threshold for defining compressed sessions",
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


def compute_daily_metrics(bars: pd.DataFrame, compression_quantile: float) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time

    rows: list[dict[str, object]] = []
    for date, day in df.groupby("date", sort=True):
        for session in SESSION_ORDER:
            start, end = SESSION_WINDOWS[session]
            window = day.loc[_window_mask(day["tod"], start, end)]
            if window.empty:
                continue
            session_high = float(window["mid_high"].max())
            session_low = float(window["mid_low"].min())
            session_range = session_high - session_low
            rows.append(
                {
                    "date": date,
                    "session": session,
                    "session_high": session_high,
                    "session_low": session_low,
                    "session_range": session_range,
                }
            )

    sessions = pd.DataFrame(rows)
    if sessions.empty:
        raise ValueError("No session rows were produced")

    threshold = float(sessions["session_range"].quantile(compression_quantile))
    sessions["compressed_flag"] = sessions["session_range"] <= threshold

    sessions["session_idx"] = sessions["session"].map({name: i for i, name in enumerate(SESSION_ORDER)})
    sessions = sessions.sort_values(["date", "session_idx"]).reset_index(drop=True)

    sessions["next_session_range"] = sessions["session_range"].shift(-1)
    sessions["next_date"] = sessions["date"].shift(-1)

    # Prevent crossing day boundary for NY -> next day Asia in this simple diagnostic.
    same_day = sessions["date"] == sessions["next_date"]
    sessions.loc[~same_day, "next_session_range"] = pd.NA

    sessions["expansion_ratio"] = sessions["next_session_range"] / sessions["session_range"]
    sessions["expansion_flag"] = sessions["expansion_ratio"] > 1.0
    sessions["compression_threshold"] = threshold

    out_cols = [
        "date",
        "session",
        "session_range",
        "compression_threshold",
        "compressed_flag",
        "next_session_range",
        "expansion_ratio",
        "expansion_flag",
    ]
    return sessions[out_cols]


def build_distribution(daily: pd.DataFrame) -> pd.DataFrame:
    compressed = daily[daily["compressed_flag"]]
    rows: list[dict[str, object]] = []
    for metric in ["session_range", "expansion_ratio"]:
        s = compressed[metric]
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _safe_q(s, q)})
    return pd.DataFrame(rows)


def build_summary(daily: pd.DataFrame, dataset_path: str, compression_quantile: float) -> dict[str, object]:
    compressed = daily[daily["compressed_flag"]].copy()
    compressed = compressed.dropna(subset=["expansion_ratio"])

    return {
        "dataset": dataset_path,
        "session_windows_utc": {
            name: {"start": start.strftime("%H:%M"), "end_exclusive": end.strftime("%H:%M")}
            for name, (start, end) in SESSION_WINDOWS.items()
        },
        "rows_analyzed": int(len(daily)),
        "compression_quantile": compression_quantile,
        "compression_threshold": float(daily["compression_threshold"].iloc[0]),
        "compressed_frequency": float(daily["compressed_flag"].mean()) if len(daily) else 0.0,
        "compressed_rows_with_next_session": int(len(compressed)),
        "expansion_probability_after_compression": float(compressed["expansion_flag"].mean()) if len(compressed) else 0.0,
        "median_expansion_ratio_after_compression": _safe_q(compressed["expansion_ratio"], 0.50),
        "p75_expansion_ratio_after_compression": _safe_q(compressed["expansion_ratio"], 0.75),
    }


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars)
    daily = compute_daily_metrics(bars, compression_quantile=args.compression_quantile)
    distribution = build_distribution(daily)
    summary = build_summary(daily, dataset_path=args.bars, compression_quantile=args.compression_quantile)

    daily_path = out_dir / "daily_metrics.csv"
    dist_path = out_dir / "distribution.csv"
    summary_path = out_dir / "summary.json"

    daily.to_csv(daily_path, index=False)
    distribution.to_csv(dist_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"rows_analyzed: {summary['rows_analyzed']}")
    print(f"compressed_frequency: {summary['compressed_frequency']:.4f}")
    print(f"expansion_probability_after_compression: {summary['expansion_probability_after_compression']:.4f}")
    print(f"median_expansion_ratio_after_compression: {summary['median_expansion_ratio_after_compression']:.4f}")

    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
