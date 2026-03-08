from __future__ import annotations

import argparse
import lzma
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from lzma import LZMAError


TICK_DTYPE = np.dtype(
    [
        ("millis", ">u4"),
        ("ask_raw", ">u4"),
        ("bid_raw", ">u4"),
        ("ask_volume", ">f4"),
        ("bid_volume", ">f4"),
    ]
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean Dukascopy .bi5 ticks and save parquet")
    parser.add_argument("--input-dir", default="data/raw/dukascopy/EURUSD/2023")
    parser.add_argument("--output-file", default="data/ticks/clean/eurusd_ticks_2023.parquet")
    parser.add_argument("--price-scale", type=float, default=100000.0)
    return parser.parse_args()


def decode_bi5(path: Path, price_scale: float) -> pd.DataFrame:
    try:
        payload = lzma.decompress(path.read_bytes())
    except LZMAError:
        return pd.DataFrame(columns=["timestamp", "bid", "ask", "mid", "spread"])
    if len(payload) == 0:
        return pd.DataFrame(columns=["timestamp", "bid", "ask", "mid", "spread"])

    arr = np.frombuffer(payload, dtype=TICK_DTYPE)
    year = int(path.parts[-4])
    month = int(path.parts[-3])
    day = int(path.parts[-2])
    hour = int(path.stem.split("h_ticks")[0])
    base_ts = pd.Timestamp(year=year, month=month, day=day, hour=hour, tz="UTC")

    ask = arr["ask_raw"].astype(np.float64) / price_scale
    bid = arr["bid_raw"].astype(np.float64) / price_scale
    ts = base_ts + pd.to_timedelta(arr["millis"].astype(np.int64), unit="ms")

    out = pd.DataFrame({"timestamp": ts, "bid": bid, "ask": ask})
    out = out.drop_duplicates(subset=["timestamp", "bid", "ask"]).sort_values("timestamp")
    out["mid"] = (out["bid"] + out["ask"]) / 2.0
    out["spread"] = out["ask"] - out["bid"]
    return out.reset_index(drop=True)


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(input_dir.rglob("*h_ticks.bi5"))
    if not files:
        raise FileNotFoundError(f"No .bi5 files found under {input_dir}")

    writer: pq.ParquetWriter | None = None
    total_rows = 0
    skipped_corrupt = 0

    for idx, file_path in enumerate(files, start=1):
        df = decode_bi5(file_path, price_scale=args.price_scale)
        if df.empty:
            skipped_corrupt += 1
            continue

        table = pa.Table.from_pandas(df, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(str(output_file), table.schema, compression="zstd")
        writer.write_table(table)
        total_rows += len(df)

        if idx % 500 == 0 or idx == len(files):
            print(f"{idx}/{len(files)} files processed, rows={total_rows}")

    if writer is None:
        raise RuntimeError("No tick rows were decoded; parquet was not written")
    writer.close()

    print(f"Saved cleaned ticks: {output_file}")
    print(f"Total rows: {total_rows}")
    print(f"Skipped empty/corrupt files: {skipped_corrupt}")


if __name__ == "__main__":
    main()
