from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


BAR_VALUE_COLUMNS = ("bid", "ask", "mid", "spread")
DEFAULT_SESSION_ROLLOVER_HOUR_UTC = 22


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate existing 15m bars into higher timeframe bars.")
    parser.add_argument("--input-file", required=True, help="Path to source parquet bars")
    parser.add_argument("--output-file", required=True, help="Path to output parquet bars")
    parser.add_argument(
        "--timeframe",
        required=True,
        choices=["4h", "1d"],
        help="Target timeframe for aggregation",
    )
    parser.add_argument(
        "--session-rollover-hour-utc",
        type=int,
        default=DEFAULT_SESSION_ROLLOVER_HOUR_UTC,
        help=(
            "Fixed UTC hour used as the FX session rollover anchor for 1d/4h aggregation. "
            "This repo defaults to 22:00 UTC to match the existing FX market-week boundary."
        ),
    )
    return parser.parse_args()


def timeframe_to_rule(timeframe: str) -> str:
    return {"4h": "4h", "1d": "1d"}[timeframe]


def validate_session_rollover_hour(session_rollover_hour_utc: int) -> None:
    if not 0 <= session_rollover_hour_utc <= 23:
        raise ValueError("session_rollover_hour_utc must be between 0 and 23")


def _metadata_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}.metadata.json")


def build_metadata(
    *,
    input_path: Path,
    timeframe: str,
    session_rollover_hour_utc: int,
) -> dict[str, str | int]:
    timestamp_label = (
        f"bar_open_utc_aligned_to_{session_rollover_hour_utc:02d}:00_rollover"
        if timeframe == "1d"
        else f"bar_open_utc_aligned_to_{session_rollover_hour_utc:02d}:00_rollover_in_4h_steps"
    )
    return {
        "source_file": str(input_path),
        "timeframe": timeframe,
        "timestamp_timezone": "UTC",
        "timestamp_convention": "bar_open",
        "session_rollover_hour_utc": session_rollover_hour_utc,
        "bucket_timestamp_label": timestamp_label,
        "session_alignment_mode": "fixed_utc_rollover",
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
    }


def aggregate_bars(
    bars: pd.DataFrame,
    timeframe: str,
    session_rollover_hour_utc: int = DEFAULT_SESSION_ROLLOVER_HOUR_UTC,
) -> pd.DataFrame:
    if bars.empty:
        return bars.copy()

    validate_session_rollover_hour(session_rollover_hour_utc)

    bars = bars.copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)
    rule = timeframe_to_rule(timeframe)
    rollover_offset = pd.Timedelta(hours=session_rollover_hour_utc)

    frames: list[pd.DataFrame] = []
    for symbol, symbol_bars in bars.groupby("symbol", sort=True):
        symbol_bars = symbol_bars.set_index("timestamp")

        # The source bars are stored at UTC bar-open timestamps. Shift by the fixed
        # FX session rollover so 1d bars open at that rollover hour and 4h bars stay
        # aligned to the same day boundary (22/02/06/10/14/18 UTC by default).
        shifted = symbol_bars.copy()
        shifted.index = shifted.index - rollover_offset
        grouped = shifted.resample(rule, label="left", closed="left")

        agg_map = {"session_label": "first"}
        for prefix in BAR_VALUE_COLUMNS:
            agg_map[f"{prefix}_open"] = "first"
            agg_map[f"{prefix}_high"] = "max"
            agg_map[f"{prefix}_low"] = "min"
            agg_map[f"{prefix}_close"] = "last"

        aggregated = grouped.agg(agg_map).dropna(subset=["mid_open", "mid_high", "mid_low", "mid_close"])
        aggregated.index = aggregated.index + rollover_offset
        aggregated = aggregated.reset_index().rename(columns={"index": "timestamp"})
        aggregated["symbol"] = symbol
        aggregated["timeframe"] = timeframe
        frames.append(aggregated)

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=bars.columns)
    ordered_columns = [
        "timestamp",
        "symbol",
        "timeframe",
        "bid_open",
        "bid_high",
        "bid_low",
        "bid_close",
        "ask_open",
        "ask_high",
        "ask_low",
        "ask_close",
        "mid_open",
        "mid_high",
        "mid_low",
        "mid_close",
        "spread_open",
        "spread_high",
        "spread_low",
        "spread_close",
        "session_label",
    ]
    return result[ordered_columns].sort_values(["symbol", "timestamp"]).reset_index(drop=True)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_file)
    output_path = Path(args.output_file)
    metadata_path = _metadata_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bars = pd.read_parquet(input_path)
    aggregated = aggregate_bars(
        bars,
        args.timeframe,
        session_rollover_hour_utc=args.session_rollover_hour_utc,
    )
    aggregated.to_parquet(output_path, index=False)
    metadata = build_metadata(
        input_path=input_path,
        timeframe=args.timeframe,
        session_rollover_hour_utc=args.session_rollover_hour_utc,
    )
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Saved {args.timeframe} bars to: {output_path}")
    print(f"Saved metadata: {metadata_path}")
    print(f"Rows: {len(aggregated)}")


if __name__ == "__main__":
    main()
