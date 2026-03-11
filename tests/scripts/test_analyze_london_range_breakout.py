from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_london_range_breakout.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("london_range_breakout", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load london range breakout script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def test_asian_range_calculation() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T00:00:00Z", "mid_high": 1.1020, "mid_low": 1.1000},
            {"timestamp": "2024-01-02T06:45:00Z", "mid_high": 1.1030, "mid_low": 1.0990},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_high": 1.1025, "mid_low": 1.1005},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_high": 1.1020, "mid_low": 1.1005},
        ]
    )

    daily = module.compute_daily_metrics(bars)
    row = daily.iloc[0]
    assert row["asian_high"] == pytest.approx(1.1030)
    assert row["asian_low"] == pytest.approx(1.0990)
    assert row["asian_range"] == pytest.approx(0.0040)


def test_breakout_detection_logic() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-03T00:00:00Z", "mid_high": 1.0050, "mid_low": 1.0020},
            {"timestamp": "2024-01-03T06:45:00Z", "mid_high": 1.0060, "mid_low": 1.0010},
            {"timestamp": "2024-01-03T07:00:00Z", "mid_high": 1.0065, "mid_low": 1.0030},
            {"timestamp": "2024-01-03T07:15:00Z", "mid_high": 1.0050, "mid_low": 1.0005},
        ]
    )

    daily = module.compute_daily_metrics(bars)
    row = daily.iloc[0]
    assert bool(row["break_above_range"]) is True
    assert bool(row["break_below_range"]) is True
    assert row["first_break_direction"] == "above"
    assert row["break_time"] == "2024-01-03T07:00:00+00:00"


def test_follow_through_computation() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-04T00:00:00Z", "mid_high": 1.0040, "mid_low": 1.0010},
            {"timestamp": "2024-01-04T06:45:00Z", "mid_high": 1.0050, "mid_low": 1.0000},
            {"timestamp": "2024-01-04T07:00:00Z", "mid_high": 1.0060, "mid_low": 1.0040},
            {"timestamp": "2024-01-04T07:15:00Z", "mid_high": 1.0080, "mid_low": 1.0020},
        ]
    )

    daily = module.compute_daily_metrics(bars)
    row = daily.iloc[0]
    assert row["max_move_after_break"] == pytest.approx(0.0030)
    assert row["max_adverse_move"] == pytest.approx(0.0030)
    assert row["follow_through_R"] == pytest.approx(0.6)
    assert row["adverse_move_R"] == pytest.approx(0.6)
