from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.data.loaders import load_bars

EVENT_RETURNS_SCRIPT = Path(__file__).resolve().parent / "analyze_event_returns.py"
SPEC = importlib.util.spec_from_file_location("analyze_event_returns", EVENT_RETURNS_SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load analyze_event_returns.py")
AER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AER)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze pairwise event combinations and forward-return asymmetries."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/event_combination_analysis",
        help="Output directory for summary and combination tables",
    )
    parser.add_argument(
        "--alignment-window-bars",
        type=int,
        default=1,
        help="Alignment window for pairwise conditions (same bar or within N bars)",
    )
    parser.add_argument(
        "--min-sample-size",
        type=int,
        default=100,
        help="Minimum sample size for top combination edge ranking",
    )
    return parser.parse_args()


def build_event_flags(
    bars: pd.DataFrame,
    impulse_lookback_bars: int = 4,
    breakout_lookback_bars: int = 20,
    compression_window_bars: int = 40,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["atr"] = AER.compute_atr(df, period=14)
    df["rolling_median_atr"] = df["atr"].rolling(
        compression_window_bars, min_periods=compression_window_bars
    ).median()
    df["compression_ratio"] = df["atr"] / df["rolling_median_atr"]
    compression_valid = df["compression_ratio"].dropna()
    p10 = float(compression_valid.quantile(0.10))
    p25 = float(compression_valid.quantile(0.25))
    p50 = float(compression_valid.quantile(0.50))

    n = len(df)
    closes = df["mid_close"].to_numpy(dtype=float)
    highs = df["mid_high"].to_numpy(dtype=float)
    lows = df["mid_low"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)

    flags = pd.DataFrame(
        {
            "timestamp": df["timestamp"],
            "impulse_direction": ["none"] * n,
            "new_high_flag": [False] * n,
            "new_low_flag": [False] * n,
            "compression_active": [False] * n,
            "is_london_open": [False] * n,
            "is_new_york_open": [False] * n,
        }
    )

    for i in range(n):
        ts = pd.Timestamp(df.iloc[i]["timestamp"])
        flags.at[i, "is_london_open"] = bool(ts.hour == 7 and ts.minute == 0)
        flags.at[i, "is_new_york_open"] = bool(ts.hour == 13 and ts.minute == 0)

        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        if i >= impulse_lookback_bars:
            move = closes[i] - closes[i - impulse_lookback_bars]
            strength_atr = abs(move) / atr[i]
            if AER.impulse_bucket(float(strength_atr)) is not None and move != 0:
                flags.at[i, "impulse_direction"] = "up" if move > 0 else "down"
        if i >= breakout_lookback_bars:
            prev_high = float(np.max(highs[i - breakout_lookback_bars : i]))
            prev_low = float(np.min(lows[i - breakout_lookback_bars : i]))
            flags.at[i, "new_high_flag"] = bool(highs[i] > prev_high)
            flags.at[i, "new_low_flag"] = bool(lows[i] < prev_low)

        bucket = AER.compression_bucket(float(df.iloc[i]["compression_ratio"]), p10, p25, p50)
        flags.at[i, "compression_active"] = bool(bucket is not None)

    return flags, closes, highs, lows, atr


def _aligned_true(series: pd.Series, idx: int, window: int) -> bool:
    left = max(0, idx - window)
    right = min(len(series), idx + window + 1)
    return bool(series.iloc[left:right].any())


def detect_combination_events(
    flags: pd.DataFrame,
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    atr: np.ndarray,
    alignment_window_bars: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    n = len(flags)
    for i in range(n):
        if i + 8 >= n:
            break
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue

        ts = pd.Timestamp(flags.iloc[i]["timestamp"])
        impulse_direction = str(flags.iloc[i]["impulse_direction"])
        compression_active = bool(flags.iloc[i]["compression_active"])
        new_high = _aligned_true(flags["new_high_flag"], i, alignment_window_bars)
        new_low = _aligned_true(flags["new_low_flag"], i, alignment_window_bars)
        london_open = _aligned_true(flags["is_london_open"], i, alignment_window_bars)
        ny_open = _aligned_true(flags["is_new_york_open"], i, alignment_window_bars)

        def add_row(name: str, direction: str) -> None:
            rows.append(
                {
                    "timestamp": ts.isoformat(),
                    "combination_name": name,
                    "direction": direction,
                    **AER.compute_forward_metrics(closes, highs, lows, atr, i, direction),
                }
            )

        # 1) impulse + new_high/new_low
        if impulse_direction == "up" and new_high:
            add_row("impulse_plus_new_high", "up")
        if impulse_direction == "down" and new_low:
            add_row("impulse_plus_new_low", "down")

        # 2) impulse + session_open
        if impulse_direction in {"up", "down"} and london_open:
            add_row("impulse_plus_london_open", impulse_direction)
        if impulse_direction in {"up", "down"} and ny_open:
            add_row("impulse_plus_new_york_open", impulse_direction)

        # 3) compression + session_open
        if compression_active and london_open:
            add_row("compression_plus_london_open", "none")
        if compression_active and ny_open:
            add_row("compression_plus_new_york_open", "none")

        # 4) compression + breakout(new_high/new_low)
        if compression_active and new_high:
            add_row("compression_plus_new_high", "up")
        if compression_active and new_low:
            add_row("compression_plus_new_low", "down")

    if not rows:
        raise ValueError("No combination events detected")
    return pd.DataFrame(rows)


def build_combination_bucket_summary(events: pd.DataFrame) -> pd.DataFrame:
    summary = (
        events.groupby(["combination_name", "direction"], dropna=False)
        .agg(
            sample_size=("timestamp", "count"),
            median_return_1_bar=("return_1_bar", "median"),
            median_return_4_bars=("return_4_bars", "median"),
            median_return_8_bars=("return_8_bars", "median"),
            median_adverse_move_4_bars=("adverse_move_4_bars", "median"),
            median_adverse_move_8_bars=("adverse_move_8_bars", "median"),
        )
        .reset_index()
    )
    summary["edge_score"] = summary["median_return_4_bars"].abs() * np.log(
        summary["sample_size"]
    )
    return summary.sort_values("edge_score", ascending=False).reset_index(drop=True)


def build_top_combination_edges(
    summary: pd.DataFrame, min_sample_size: int
) -> pd.DataFrame:
    filtered = summary[summary["sample_size"] >= min_sample_size].copy()
    filtered["abs_median_return_4_bars"] = filtered["median_return_4_bars"].abs()
    return filtered.sort_values("abs_median_return_4_bars", ascending=False).head(15)[
        [
            "combination_name",
            "direction",
            "sample_size",
            "median_return_1_bar",
            "median_return_4_bars",
            "median_return_8_bars",
            "median_adverse_move_4_bars",
            "median_adverse_move_8_bars",
            "edge_score",
        ]
    ]


def build_summary_json(
    events: pd.DataFrame, summary: pd.DataFrame, top_edges: pd.DataFrame, min_sample_size: int
) -> dict[str, object]:
    totals = (
        events.groupby("combination_name")["timestamp"].count().sort_values(ascending=False)
    )
    return {
        "total_combination_events": int(len(events)),
        "total_events_by_combination": {k: int(v) for k, v in totals.items()},
        "total_unique_combinations": int(summary["combination_name"].nunique()),
        "sample_size_threshold": int(min_sample_size),
        "top_combination_edges": top_edges.to_dict(orient="records"),
        "interpretation_notes": [
            "positive median_return_4_bars implies continuation in event direction for directional combinations",
            "negative median_return_4_bars implies reversal against event direction for directional combinations",
            "direction=none combinations are unaligned close-to-close return effects",
            "combination edges with small sample sizes should be treated as exploratory",
        ],
    }


def run_analysis(
    bars_path: str,
    output_dir: str,
    alignment_window_bars: int,
    min_sample_size: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    bars = load_bars(bars_path).copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)

    flags, closes, highs, lows, atr = build_event_flags(bars)
    events = detect_combination_events(
        flags,
        closes=closes,
        highs=highs,
        lows=lows,
        atr=atr,
        alignment_window_bars=alignment_window_bars,
    )
    summary = build_combination_bucket_summary(events)
    top_edges = build_top_combination_edges(summary, min_sample_size=min_sample_size)
    summary_json = build_summary_json(
        events, summary, top_edges, min_sample_size=min_sample_size
    )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "event_combinations.csv"
    summary_path = out_dir / "combination_bucket_summary.csv"
    top_path = out_dir / "top_combination_edges.csv"
    json_path = out_dir / "summary.json"

    events.to_csv(events_path, index=False)
    summary.to_csv(summary_path, index=False)
    top_edges.to_csv(top_path, index=False)
    json_path.write_text(json.dumps(summary_json, indent=2), encoding="utf-8")
    return events, summary, top_edges, summary_json


def print_console_top_edges(top_edges: pd.DataFrame) -> None:
    if top_edges.empty:
        print("No combination edges passed the sample-size filter.")
        return
    table = top_edges[
        [
            "combination_name",
            "direction",
            "sample_size",
            "median_return_4_bars",
            "median_adverse_move_4_bars",
        ]
    ].copy()
    table = table.rename(columns={"sample_size": "sample"})
    print("\nTop 15 combination edges by |median_return_4_bars|:")
    print(table.to_string(index=False))


def main() -> None:
    args = parse_args()
    events, summary, top_edges, summary_json = run_analysis(
        bars_path=args.bars,
        output_dir=args.output_dir,
        alignment_window_bars=args.alignment_window_bars,
        min_sample_size=args.min_sample_size,
    )

    print(f"total_combination_events: {len(events)}")
    print(f"unique_combinations: {summary['combination_name'].nunique()}")
    print(f"saved: {Path(args.output_dir) / 'event_combinations.csv'}")
    print(f"saved: {Path(args.output_dir) / 'combination_bucket_summary.csv'}")
    print(f"saved: {Path(args.output_dir) / 'top_combination_edges.csv'}")
    print(f"saved: {Path(args.output_dir) / 'summary.json'}")
    print_console_top_edges(top_edges)
    print(
        f"\nSummary: sample_size_threshold={summary_json['sample_size_threshold']}, "
        f"top_edges={len(summary_json['top_combination_edges'])}"
    )


if __name__ == "__main__":
    main()
