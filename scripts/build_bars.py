from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build 15m bars from cleaned ticks parquet")
    parser.add_argument("--input-file", default="data/ticks/clean/eurusd_ticks_2023.parquet")
    parser.add_argument("--output-file", default="data/bars/15m/eurusd_bars_15m_2023_raw.parquet")
    parser.add_argument("--symbol", default="EURUSD")
    return parser.parse_args()


def build_ohlc(df: pd.DataFrame, value_col: str, prefix: str) -> pd.DataFrame:
    ohlc = df[value_col].resample("15min").ohlc().dropna()
    ohlc.columns = [f"{prefix}_open", f"{prefix}_high", f"{prefix}_low", f"{prefix}_close"]
    return ohlc


def main() -> None:
    args = parse_args()
    input_file = Path(args.input_file)
    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    ticks = pd.read_parquet(input_file, columns=["timestamp", "bid", "ask", "mid", "spread"])
    ticks["timestamp"] = pd.to_datetime(ticks["timestamp"], utc=True)
    ticks = ticks.drop_duplicates(subset=["timestamp", "bid", "ask"]).sort_values("timestamp")
    ticks = ticks.set_index("timestamp")

    bid_bars = build_ohlc(ticks, "bid", "bid")
    ask_bars = build_ohlc(ticks, "ask", "ask")
    mid_bars = build_ohlc(ticks, "mid", "mid")
    spread_bars = build_ohlc(ticks, "spread", "spread")

    bars = pd.concat([bid_bars, ask_bars, mid_bars, spread_bars], axis=1).dropna().reset_index()
    bars = bars.rename(columns={"timestamp": "timestamp"})
    bars["symbol"] = str(args.symbol).upper()
    bars["timeframe"] = "15m"

    ordered_cols = [
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
    ]
    bars = bars[ordered_cols].sort_values("timestamp").reset_index(drop=True)
    bars.to_parquet(output_file, index=False)

    print(f"Saved bars: {output_file}")
    print(f"Bars: {len(bars)}")


if __name__ == "__main__":
    main()
