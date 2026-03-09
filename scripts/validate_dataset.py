from __future__ import annotations

import argparse
import json
import lzma
import sys
from pathlib import Path

import pandas as pd
from lzma import LZMAError

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate cleaned ticks and 15m bars for a target year")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--ticks-file", required=True)
    parser.add_argument("--bars-file", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def collect_raw_file_stats(raw_dir: Path) -> dict[str, int]:
    raw_files = sorted(raw_dir.rglob("*h_ticks.bi5"))
    corrupt_or_unreadable = 0
    empty_payload_files = 0

    for file_path in raw_files:
        try:
            payload = lzma.decompress(file_path.read_bytes())
        except LZMAError:
            corrupt_or_unreadable += 1
            continue
        if len(payload) == 0:
            empty_payload_files += 1

    skipped_files = corrupt_or_unreadable + empty_payload_files
    return {
        "total_files": len(raw_files),
        "corrupt_or_unreadable_files": corrupt_or_unreadable,
        "empty_payload_files": empty_payload_files,
        "skipped_files": skipped_files,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    year = args.year
    raw_dir = Path(args.raw_dir)
    ticks_file = Path(args.ticks_file)
    bars_file = Path(args.bars_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_stats = collect_raw_file_stats(raw_dir)

    ticks = pd.read_parquet(ticks_file, columns=["timestamp"])
    tick_count = int(len(ticks))

    bars = pd.read_parquet(bars_file)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)

    expected_index = pd.date_range(
        f"{year}-01-01 00:00:00+00:00",
        f"{year}-12-31 23:45:00+00:00",
        freq="15min",
    )
    expected_bar_count = int(len(expected_index))
    actual_bar_count = int(len(bars))

    diffs = bars["timestamp"].diff().dropna()
    expected_delta = pd.Timedelta(minutes=15)
    gaps = diffs[diffs > expected_delta]
    gap_count = int(len(gaps))
    longest_gap_minutes = float((gaps.max() / pd.Timedelta(minutes=1)) if len(gaps) else 0.0)

    continuity = {
        "expected_bar_count_full_year": expected_bar_count,
        "actual_bar_count": actual_bar_count,
        "gaps_gt_15m": gap_count,
        "longest_gap_minutes": longest_gap_minutes,
    }
    write_json(output_dir / "bar_continuity.json", continuity)

    spread = bars["spread_close"]
    spread_stats = {
        "min_spread": float(spread.min()),
        "median_spread": float(spread.median()),
        "mean_spread": float(spread.mean()),
        "p75_spread": float(spread.quantile(0.75)),
        "p95_spread": float(spread.quantile(0.95)),
        "p99_spread": float(spread.quantile(0.99)),
        "max_spread": float(spread.max()),
    }
    write_json(output_dir / "spread_stats.json", spread_stats)

    bars["date"] = bars["timestamp"].dt.date
    counts = bars.groupby("date").size().rename("bar_count").to_frame()
    all_days = pd.DataFrame(
        {"date": pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D").date}
    )
    daily = all_days.merge(counts, on="date", how="left").fillna({"bar_count": 0})
    daily["bar_count"] = daily["bar_count"].astype(int)
    daily["incomplete_day"] = daily["bar_count"] < 96
    daily.to_csv(output_dir / "daily_bar_counts.csv", index=False)

    summary = {
        "tick_count": tick_count,
        "bar_count": actual_bar_count,
        "gap_count": gap_count,
        "largest_gap_minutes": longest_gap_minutes,
        "spread_statistics": spread_stats,
        "date_range": {
            "start": bars["timestamp"].min().isoformat() if not bars.empty else None,
            "end": bars["timestamp"].max().isoformat() if not bars.empty else None,
        },
        "raw_file_stats": raw_stats,
    }
    write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    print(f"Wrote validation outputs to: {output_dir}")


if __name__ == "__main__":
    main()
