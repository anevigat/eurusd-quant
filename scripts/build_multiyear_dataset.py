from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

BAR_FREQUENCY = pd.Timedelta(minutes=15)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a continuous EURUSD 15m bars dataset from yearly parquet files."
    )
    parser.add_argument("--input-dir", default="data/bars/15m", help="Directory with yearly bar files")
    parser.add_argument("--start-year", type=int, default=2018, help="First year (inclusive)")
    parser.add_argument("--end-year", type=int, default=2024, help="Last year (inclusive)")
    parser.add_argument(
        "--output-file",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Output parquet file",
    )
    return parser.parse_args()


def validate_strictly_increasing(timestamps: pd.Series, context: str) -> None:
    if timestamps.empty:
        return
    deltas = timestamps.diff().dropna()
    if (deltas <= pd.Timedelta(0)).any():
        raise ValueError(f"Timestamps are not strictly increasing in {context}")


def load_and_clean_year(path: Path, year: int) -> tuple[pd.DataFrame, int]:
    if not path.exists():
        raise FileNotFoundError(f"Missing yearly bars file: {path}")

    df = pd.read_parquet(path)
    if "timestamp" not in df.columns:
        raise ValueError(f"File has no timestamp column: {path}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp", kind="mergesort").reset_index(drop=True)

    duplicate_count = int(df["timestamp"].duplicated().sum())
    if duplicate_count:
        df = df.drop_duplicates(subset=["timestamp"], keep="first").reset_index(drop=True)

    validate_strictly_increasing(df["timestamp"], f"year {year}")
    return df, duplicate_count


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    years = list(range(args.start_year, args.end_year + 1))
    frames: list[pd.DataFrame] = []

    total_duplicates_removed = 0
    total_overlaps_removed = 0
    prev_last_timestamp: pd.Timestamp | None = None

    for year in years:
        year_file = input_dir / f"eurusd_bars_15m_{year}.parquet"
        year_df, duplicate_count = load_and_clean_year(year_file, year)
        total_duplicates_removed += duplicate_count

        overlap_count = 0
        if prev_last_timestamp is not None and not year_df.empty:
            overlap_mask = year_df["timestamp"] <= prev_last_timestamp
            overlap_count = int(overlap_mask.sum())
            if overlap_count:
                year_df = year_df.loc[~overlap_mask].reset_index(drop=True)

        total_overlaps_removed += overlap_count
        if not year_df.empty:
            prev_last_timestamp = year_df["timestamp"].iloc[-1]
            frames.append(year_df)

        print(
            f"{year}: rows={len(year_df)} "
            f"duplicates_removed={duplicate_count} overlaps_removed={overlap_count}"
        )

    if not frames:
        raise ValueError("No rows loaded from yearly files")

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.sort_values("timestamp", kind="mergesort").reset_index(drop=True)

    cross_year_duplicates = int(merged["timestamp"].duplicated().sum())
    if cross_year_duplicates:
        merged = merged.drop_duplicates(subset=["timestamp"], keep="first").reset_index(drop=True)
        total_duplicates_removed += cross_year_duplicates

    validate_strictly_increasing(merged["timestamp"], "merged dataset")

    gaps = merged["timestamp"].diff().dropna()
    large_gaps = gaps[gaps > BAR_FREQUENCY]
    gap_count = int(len(large_gaps))
    largest_gap = str(large_gaps.max()) if gap_count else "0 days 00:00:00"

    merged.to_parquet(output_file, index=False)

    print("")
    print(f"Saved merged dataset to: {output_file}")
    print(f"Total rows: {len(merged)}")
    print(f"Start date: {merged['timestamp'].iloc[0].isoformat()}")
    print(f"End date: {merged['timestamp'].iloc[-1].isoformat()}")
    print(f"Gaps > 15 minutes: {gap_count}")
    print(f"Largest gap: {largest_gap}")
    print(f"Total duplicates removed: {total_duplicates_removed}")
    print(f"Total overlap rows removed: {total_overlaps_removed}")


if __name__ == "__main__":
    main()
