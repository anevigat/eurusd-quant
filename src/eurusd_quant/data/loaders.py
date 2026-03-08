from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = [
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


def load_bars(path: str | Path) -> pd.DataFrame:
    df = pd.read_parquet(path)

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Input parquet is missing columns: {missing}")

    out = df[REQUIRED_COLUMNS].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)

    if not out["timestamp"].is_monotonic_increasing:
        raise ValueError("Input bars must be sorted by ascending timestamp")

    if (out["symbol"] != "EURUSD").any():
        raise ValueError("MVP only supports symbol EURUSD")

    if (out["timeframe"] != "15m").any():
        raise ValueError("MVP only supports timeframe 15m")

    return out.reset_index(drop=True)
