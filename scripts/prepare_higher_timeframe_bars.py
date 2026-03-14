from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


BAR_VALUE_COLUMNS = ("bid", "ask", "mid", "spread")


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
    return parser.parse_args()


def timeframe_to_rule(timeframe: str) -> str:
    return {"4h": "4h", "1d": "1d"}[timeframe]


def aggregate_bars(bars: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if bars.empty:
        return bars.copy()

    bars = bars.copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)
    rule = timeframe_to_rule(timeframe)

    frames: list[pd.DataFrame] = []
    for symbol, symbol_bars in bars.groupby("symbol", sort=True):
        symbol_bars = symbol_bars.set_index("timestamp")
        grouped = symbol_bars.resample(rule, label="left", closed="left")

        agg_map = {"session_label": "first"}
        for prefix in BAR_VALUE_COLUMNS:
            agg_map[f"{prefix}_open"] = "first"
            agg_map[f"{prefix}_high"] = "max"
            agg_map[f"{prefix}_low"] = "min"
            agg_map[f"{prefix}_close"] = "last"

        aggregated = grouped.agg(agg_map).dropna(subset=["mid_open", "mid_high", "mid_low", "mid_close"]).reset_index()
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
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bars = pd.read_parquet(input_path)
    aggregated = aggregate_bars(bars, args.timeframe)
    aggregated.to_parquet(output_path, index=False)

    print(f"Saved {args.timeframe} bars to: {output_path}")
    print(f"Rows: {len(aggregated)}")


if __name__ == "__main__":
    main()
