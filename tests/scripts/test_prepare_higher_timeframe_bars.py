from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "prepare_higher_timeframe_bars.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("prepare_higher_timeframe_bars", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load higher timeframe aggregation script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_aggregate_bars_builds_daily_rows() -> None:
    module = load_script_module()
    bars = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2024-01-01 00:00:00", tz="UTC"),
                "symbol": "EURUSD",
                "timeframe": "15m",
                "bid_open": 1.1000,
                "bid_high": 1.1010,
                "bid_low": 1.0990,
                "bid_close": 1.1005,
                "ask_open": 1.1001,
                "ask_high": 1.1011,
                "ask_low": 1.0991,
                "ask_close": 1.1006,
                "mid_open": 1.10005,
                "mid_high": 1.10105,
                "mid_low": 1.09905,
                "mid_close": 1.10055,
                "spread_open": 0.0001,
                "spread_high": 0.0001,
                "spread_low": 0.0001,
                "spread_close": 0.0001,
                "session_label": "asia",
            },
            {
                "timestamp": pd.Timestamp("2024-01-01 00:15:00", tz="UTC"),
                "symbol": "EURUSD",
                "timeframe": "15m",
                "bid_open": 1.1005,
                "bid_high": 1.1020,
                "bid_low": 1.1000,
                "bid_close": 1.1015,
                "ask_open": 1.1006,
                "ask_high": 1.1021,
                "ask_low": 1.1001,
                "ask_close": 1.1016,
                "mid_open": 1.10055,
                "mid_high": 1.10205,
                "mid_low": 1.10005,
                "mid_close": 1.10155,
                "spread_open": 0.0001,
                "spread_high": 0.0001,
                "spread_low": 0.0001,
                "spread_close": 0.0001,
                "session_label": "asia",
            },
        ]
    )

    aggregated = module.aggregate_bars(bars, "1d")

    assert len(aggregated) == 1
    assert aggregated.loc[0, "timeframe"] == "1d"
    assert aggregated.loc[0, "bid_open"] == 1.1000
    assert aggregated.loc[0, "bid_close"] == 1.1015
    assert aggregated.loc[0, "bid_high"] == 1.1020
    assert aggregated.loc[0, "bid_low"] == 1.0990
