from __future__ import annotations

import argparse
from pathlib import Path
import re

import pandas as pd
import pyarrow.parquet as pq

VALUE_COLUMNS = ("bid", "ask", "mid", "spread")
OPEN_COLUMNS = [f"{col}_open" for col in VALUE_COLUMNS]
HIGH_COLUMNS = [f"{col}_high" for col in VALUE_COLUMNS]
LOW_COLUMNS = [f"{col}_low" for col in VALUE_COLUMNS]
CLOSE_COLUMNS = [f"{col}_close" for col in VALUE_COLUMNS]
AGG_COLUMNS = ["first_ts", "last_ts", *OPEN_COLUMNS, *HIGH_COLUMNS, *LOW_COLUMNS, *CLOSE_COLUMNS]
KNOWN_FX_CCY = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CHF", "CAD"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build 15m bars from cleaned ticks parquet")
    parser.add_argument("--input-file", default="data/ticks/clean/eurusd_ticks_2023.parquet")
    parser.add_argument("--output-file", default="data/bars/15m/eurusd_bars_15m_2023_raw.parquet")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument(
        "--row-groups-per-batch",
        type=int,
        default=512,
        help="Number of parquet row groups to read/process per batch",
    )
    return parser.parse_args()


def infer_symbol_from_path(path: Path) -> str | None:
    def is_fx_pair(token: str) -> bool:
        return (
            len(token) == 6
            and token.isalpha()
            and token[:3] in KNOWN_FX_CCY
            and token[3:] in KNOWN_FX_CCY
            and token[:3] != token[3:]
        )

    for part in path.parts:
        token = str(part).upper()
        if is_fx_pair(token):
            return token
    for token in re.split(r"[^A-Za-z]", path.stem):
        candidate = token.upper()
        if is_fx_pair(candidate):
            return candidate
    return None


def empty_bar_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=AGG_COLUMNS)


def build_batch_bars(ticks: pd.DataFrame) -> pd.DataFrame:
    if ticks.empty:
        return empty_bar_frame()

    ticks = ticks.dropna(subset=["timestamp", *VALUE_COLUMNS])
    if ticks.empty:
        return empty_bar_frame()

    ticks["timestamp"] = pd.to_datetime(ticks["timestamp"], utc=True)
    ticks = ticks.drop_duplicates(subset=["timestamp", "bid", "ask"])
    ticks = ticks.sort_values("timestamp", kind="mergesort")
    if ticks.empty:
        return empty_bar_frame()

    ticks["bar_ts"] = ticks["timestamp"].dt.floor("15min")
    grouped = ticks.groupby("bar_ts", sort=True)

    out = pd.DataFrame(index=grouped.size().index)
    out["first_ts"] = grouped["timestamp"].first()
    out["last_ts"] = grouped["timestamp"].last()

    for col in VALUE_COLUMNS:
        g = grouped[col]
        out[f"{col}_open"] = g.first()
        out[f"{col}_high"] = g.max()
        out[f"{col}_low"] = g.min()
        out[f"{col}_close"] = g.last()

    return out


def merge_batch_bars(accum: pd.DataFrame, batch: pd.DataFrame) -> pd.DataFrame:
    if batch.empty:
        return accum
    if accum.empty:
        return batch.copy()

    common_index = accum.index.intersection(batch.index)
    new_index = batch.index.difference(accum.index)

    if not common_index.empty:
        existing = accum.loc[common_index]
        incoming = batch.loc[common_index]

        use_incoming_open = incoming["first_ts"] < existing["first_ts"]
        use_incoming_close = incoming["last_ts"] > existing["last_ts"]

        accum.loc[common_index, "first_ts"] = existing["first_ts"].where(
            existing["first_ts"] <= incoming["first_ts"],
            incoming["first_ts"],
        )
        accum.loc[common_index, "last_ts"] = existing["last_ts"].where(
            existing["last_ts"] >= incoming["last_ts"],
            incoming["last_ts"],
        )

        for col in OPEN_COLUMNS:
            accum.loc[common_index, col] = existing[col].where(use_incoming_open, incoming[col])
        for col in CLOSE_COLUMNS:
            accum.loc[common_index, col] = existing[col].where(~use_incoming_close, incoming[col])
        for col in HIGH_COLUMNS:
            accum.loc[common_index, col] = existing[col].where(existing[col] >= incoming[col], incoming[col])
        for col in LOW_COLUMNS:
            accum.loc[common_index, col] = existing[col].where(existing[col] <= incoming[col], incoming[col])

    if not new_index.empty:
        accum = pd.concat([accum, batch.loc[new_index]], axis=0)

    return accum


def main() -> None:
    args = parse_args()
    input_file = Path(args.input_file)
    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if args.row_groups_per_batch < 1:
        raise ValueError("--row-groups-per-batch must be >= 1")

    symbol = str(args.symbol).upper()
    if symbol == "EURUSD":
        inferred = infer_symbol_from_path(input_file)
        if inferred and inferred != symbol:
            print(f"Info: inferred symbol '{inferred}' from input path; overriding default EURUSD.")
            symbol = inferred

    parquet_file = pq.ParquetFile(input_file)
    total_row_groups = parquet_file.num_row_groups
    print(
        "Building 15m bars from cleaned ticks",
        f"(row_groups={total_row_groups}, batch={args.row_groups_per_batch})",
    )

    accum = empty_bar_frame()
    processed_row_groups = 0
    processed_rows = 0
    for start in range(0, total_row_groups, args.row_groups_per_batch):
        end = min(start + args.row_groups_per_batch, total_row_groups)
        rg_indices = list(range(start, end))
        table = parquet_file.read_row_groups(rg_indices, columns=["timestamp", "bid", "ask", "mid", "spread"])
        ticks_batch = table.to_pandas()
        processed_rows += len(ticks_batch)

        batch_bars = build_batch_bars(ticks_batch)
        if not batch_bars.empty:
            accum = merge_batch_bars(accum, batch_bars)

        processed_row_groups = end
        print(
            f"Processed row groups {processed_row_groups}/{total_row_groups} "
            f"(ticks read: {processed_rows:,}, bars so far: {len(accum):,})"
        )

    if accum.empty:
        bars = pd.DataFrame(
            columns=[
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
        )
    else:
        bars = accum.sort_index().reset_index()
        if "timestamp" not in bars.columns:
            if "bar_ts" in bars.columns:
                bars = bars.rename(columns={"bar_ts": "timestamp"})
            else:
                first_col = bars.columns[0]
                bars = bars.rename(columns={first_col: "timestamp"})
        bars = bars.drop(columns=["first_ts", "last_ts"], errors="ignore")
        bars["symbol"] = symbol
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
