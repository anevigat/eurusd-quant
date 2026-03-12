from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "analyze_range_midpoint_reversion.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("range_midpoint_reversion", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load range midpoint reversion script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_asian_midpoint_touch_detection() -> None:
    module = load_script_module()
    rows = [
        {"timestamp": "2024-01-01T00:00:00Z", "mid_open": 1.1000, "mid_high": 1.1010, "mid_low": 1.0990, "mid_close": 1.1000},
        {"timestamp": "2024-01-01T06:45:00Z", "mid_open": 1.1000, "mid_high": 1.1020, "mid_low": 1.0980, "mid_close": 1.1010},
        {"timestamp": "2024-01-01T07:00:00Z", "mid_open": 1.0998, "mid_high": 1.1002, "mid_low": 1.0994, "mid_close": 1.1000},
        {"timestamp": "2024-01-01T13:00:00Z", "mid_open": 1.1001, "mid_high": 1.1006, "mid_low": 1.0999, "mid_close": 1.1002},
        {"timestamp": "2024-01-02T00:00:00Z", "mid_open": 1.1010, "mid_high": 1.1020, "mid_low": 1.1000, "mid_close": 1.1010},
        {"timestamp": "2024-01-02T06:45:00Z", "mid_open": 1.1010, "mid_high": 1.1030, "mid_low": 1.0990, "mid_close": 1.1020},
        {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1010, "mid_high": 1.1012, "mid_low": 1.1008, "mid_close": 1.1011},
        {"timestamp": "2024-01-02T13:00:00Z", "mid_open": 1.1011, "mid_high": 1.1013, "mid_low": 1.1009, "mid_close": 1.1012},
    ]
    daily = module.compute_daily_metrics(make_bars(rows))
    row = daily[daily["date"] == "2024-01-02"].iloc[0]
    assert row["asian_midpoint"] == pytest.approx(1.1010)
    assert bool(row["asian_midpoint_hit_london"]) is True


def test_prev_day_midpoint_computed() -> None:
    module = load_script_module()
    rows = [
        {"timestamp": "2024-01-01T00:00:00Z", "mid_open": 1.1000, "mid_high": 1.1100, "mid_low": 1.0900, "mid_close": 1.1000},
        {"timestamp": "2024-01-01T23:45:00Z", "mid_open": 1.1000, "mid_high": 1.1090, "mid_low": 1.0910, "mid_close": 1.1010},
        {"timestamp": "2024-01-02T00:00:00Z", "mid_open": 1.1010, "mid_high": 1.1030, "mid_low": 1.0990, "mid_close": 1.1020},
        {"timestamp": "2024-01-02T06:45:00Z", "mid_open": 1.1020, "mid_high": 1.1040, "mid_low": 1.0980, "mid_close": 1.1015},
        {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1000, "mid_high": 1.1010, "mid_low": 1.0990, "mid_close": 1.1005},
        {"timestamp": "2024-01-02T13:00:00Z", "mid_open": 1.1005, "mid_high": 1.1015, "mid_low": 1.0995, "mid_close": 1.1007},
    ]

    daily = module.compute_daily_metrics(make_bars(rows))
    row = daily[daily["date"] == "2024-01-02"].iloc[0]
    assert row["prev_day_midpoint"] == pytest.approx(1.1000)
