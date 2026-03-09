from __future__ import annotations

import argparse
import json
import lzma
import sys
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.dataset as ds
from lzma import LZMAError

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

BAR_FREQ = "15min"
NY_TZ = "America/New_York"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate cleaned ticks and 15m bars for yearly or multi-year ranges"
    )
    parser.add_argument("--year", type=int, help="Optional single year convenience mode")
    parser.add_argument("--start-date", help="YYYY-MM-DD UTC")
    parser.add_argument("--end-date", help="YYYY-MM-DD UTC (inclusive)")
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--ticks-file", required=True)
    parser.add_argument("--bars-file", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def resolve_date_range(args: argparse.Namespace) -> tuple[date, date]:
    if args.year is not None and (args.start_date or args.end_date):
        raise ValueError("Use either --year OR --start-date/--end-date")

    if args.year is not None:
        return date(args.year, 1, 1), date(args.year, 12, 31)

    if not args.start_date or not args.end_date:
        raise ValueError("--start-date and --end-date are required when --year is not used")

    start_dt = date.fromisoformat(args.start_date)
    end_dt = date.fromisoformat(args.end_date)
    if end_dt < start_dt:
        raise ValueError("--end-date must be >= --start-date")
    return start_dt, end_dt


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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def count_tick_rows(ticks_path: Path) -> int:
    return int(ds.dataset(str(ticks_path), format="parquet").count_rows())


def is_market_closed_utc(ts_utc: pd.Timestamp) -> bool:
    if ts_utc.tz is None:
        ts_utc = ts_utc.tz_localize("UTC")
    ny = ts_utc.tz_convert(NY_TZ)
    weekday = ny.weekday()
    minute_of_day = ny.hour * 60 + ny.minute
    friday_close_minute = 17 * 60

    if weekday == 5:
        return True
    if weekday == 4 and minute_of_day >= friday_close_minute:
        return True
    if weekday == 6 and minute_of_day < friday_close_minute:
        return True
    return False


def classify_gaps(bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame(
            columns=["prev_timestamp", "timestamp", "gap_minutes", "expected_market_closed"]
        )

    expected_delta = pd.Timedelta(BAR_FREQ)
    rows: list[dict[str, Any]] = []
    ts = bars["timestamp"]
    diffs = ts.diff()

    for idx in diffs[diffs > expected_delta].index:
        prev_ts = ts.iloc[idx - 1]
        curr_ts = ts.iloc[idx]
        missing = pd.date_range(
            prev_ts + expected_delta,
            curr_ts - expected_delta,
            freq=BAR_FREQ,
            tz="UTC",
        )
        expected_market_closed = bool(len(missing) > 0 and all(is_market_closed_utc(t) for t in missing))
        gap_minutes = float((curr_ts - prev_ts) / pd.Timedelta(minutes=1))
        rows.append(
            {
                "prev_timestamp": prev_ts,
                "timestamp": curr_ts,
                "gap_minutes": gap_minutes,
                "expected_market_closed": expected_market_closed,
            }
        )
    return pd.DataFrame(rows)


def expected_open_bars_for_day(day: date) -> int:
    day_start = pd.Timestamp(datetime.combine(day, time(0, 0)), tz="UTC")
    day_end = day_start + pd.Timedelta(days=1) - pd.Timedelta(BAR_FREQ)
    stamps = pd.date_range(day_start, day_end, freq=BAR_FREQ)
    return int(sum(not is_market_closed_utc(ts) for ts in stamps))


def spread_stats(bars: pd.DataFrame) -> dict[str, float]:
    spread = bars["spread_close"]
    return {
        "min_spread": float(spread.min()),
        "median_spread": float(spread.median()),
        "mean_spread": float(spread.mean()),
        "p75_spread": float(spread.quantile(0.75)),
        "p95_spread": float(spread.quantile(0.95)),
        "p99_spread": float(spread.quantile(0.99)),
        "max_spread": float(spread.max()),
    }


def main() -> None:
    args = parse_args()
    start_date, end_date = resolve_date_range(args)

    raw_dir = Path(args.raw_dir)
    ticks_file = Path(args.ticks_file)
    bars_file = Path(args.bars_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_stats = collect_raw_file_stats(raw_dir)
    tick_count = count_tick_rows(ticks_file)

    bars = pd.read_parquet(bars_file)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)

    range_start = pd.Timestamp(datetime.combine(start_date, time(0, 0)), tz="UTC")
    range_end = pd.Timestamp(datetime.combine(end_date, time(23, 45)), tz="UTC")
    bars = bars[(bars["timestamp"] >= range_start) & (bars["timestamp"] <= range_end)].reset_index(
        drop=True
    )

    expected_requested_range_bar_count = int(len(pd.date_range(range_start, range_end, freq=BAR_FREQ)))
    expected_full_year_bar_count = None
    if (
        start_date.month == 1
        and start_date.day == 1
        and end_date.month == 12
        and end_date.day == 31
        and start_date.year == end_date.year
    ):
        expected_full_year_bar_count = expected_requested_range_bar_count

    actual_bar_count = int(len(bars))
    gaps_df = classify_gaps(bars)
    total_gap_count = int(len(gaps_df))
    unexpected_gaps = gaps_df[~gaps_df["expected_market_closed"]] if not gaps_df.empty else gaps_df
    unexpected_gap_count = int(len(unexpected_gaps))
    largest_gap_minutes = float(gaps_df["gap_minutes"].max()) if not gaps_df.empty else 0.0
    largest_unexpected_gap_minutes = (
        float(unexpected_gaps["gap_minutes"].max()) if not unexpected_gaps.empty else 0.0
    )

    continuity = {
        "expected_requested_range_bar_count": expected_requested_range_bar_count,
        "expected_full_year_bar_count": expected_full_year_bar_count,
        "actual_bar_count": actual_bar_count,
        "total_gap_count": total_gap_count,
        "unexpected_gap_count": unexpected_gap_count,
        "largest_gap_minutes": largest_gap_minutes,
        "largest_unexpected_gap_minutes": largest_unexpected_gap_minutes,
    }
    write_json(output_dir / "bar_continuity.json", continuity)

    spread_summary = spread_stats(bars)
    write_json(output_dir / "spread_stats.json", spread_summary)

    bars["date"] = bars["timestamp"].dt.date
    actual_daily = bars.groupby("date").size().rename("bar_count").to_frame()
    all_days = pd.DataFrame({"date": pd.date_range(start_date, end_date, freq="D").date})
    all_days["expected_open_bars"] = all_days["date"].map(expected_open_bars_for_day)

    daily = all_days.merge(actual_daily, on="date", how="left").fillna({"bar_count": 0})
    daily["bar_count"] = daily["bar_count"].astype(int)
    daily["missing_open_bars"] = daily["expected_open_bars"] - daily["bar_count"]
    daily["unexpected_incomplete_day"] = daily["missing_open_bars"] > 0
    daily["weekday"] = pd.to_datetime(daily["date"]).dt.day_name()
    daily.to_csv(output_dir / "daily_bar_counts.csv", index=False)

    summary = {
        "tick_count": tick_count,
        "raw_files_scanned": raw_stats["total_files"],
        "corrupt_or_unreadable": raw_stats["corrupt_or_unreadable_files"],
        "skipped_files": raw_stats["skipped_files"],
        "expected_full_year_bar_count": expected_full_year_bar_count,
        "expected_requested_range_bar_count": expected_requested_range_bar_count,
        "actual_bar_count": actual_bar_count,
        "total_gap_count": total_gap_count,
        "unexpected_gap_count": unexpected_gap_count,
        "largest_gap_minutes": largest_gap_minutes,
        "largest_unexpected_gap_minutes": largest_unexpected_gap_minutes,
        "spread_stats": spread_summary,
        "date_range": {
            "start": bars["timestamp"].min().isoformat() if not bars.empty else None,
            "end": bars["timestamp"].max().isoformat() if not bars.empty else None,
        },
    }
    write_json(output_dir / "summary.json", summary)

    print(json.dumps(summary, indent=2))
    print(f"Wrote validation outputs to: {output_dir}")


if __name__ == "__main__":
    main()
