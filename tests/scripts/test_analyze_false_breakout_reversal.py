from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_false_breakout_reversal.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_false_breakout_reversal", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load false-breakout module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_false_break_up_then_reversal() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T00:00:00Z", "mid_open": 1.1000, "mid_high": 1.1010, "mid_low": 1.0990, "mid_close": 1.1002},
            {"timestamp": "2024-01-02T06:45:00Z", "mid_open": 1.1002, "mid_high": 1.1010, "mid_low": 1.0990, "mid_close": 1.1001},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1001, "mid_high": 1.1012, "mid_low": 1.1000, "mid_close": 1.1011},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.1011, "mid_high": 1.1011, "mid_low": 1.1000, "mid_close": 1.1008},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.1008, "mid_high": 1.1009, "mid_low": 1.0997, "mid_close": 1.0999},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_open": 1.0999, "mid_high": 1.1002, "mid_low": 1.0994, "mid_close": 1.0996},
            {"timestamp": "2024-01-02T08:00:00Z", "mid_open": 1.0996, "mid_high": 1.1001, "mid_low": 1.0995, "mid_close": 1.0999},
        ]
    )

    daily = module.compute_daily_metrics(bars, return_inside_bars=3, reversal_horizon_bars=4)
    row = daily.iloc[0]
    assert bool(row["false_break_flag"]) is True
    assert row["false_break_direction"] == "false_break_up"
    assert row["follow_through_R"] == pytest.approx((1.1008 - 1.0994) / (1.1010 - 1.0990))


def test_summary_fields_present() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T00:00:00Z", "mid_open": 1.2000, "mid_high": 1.2010, "mid_low": 1.1990, "mid_close": 1.2002},
            {"timestamp": "2024-01-02T06:45:00Z", "mid_open": 1.2002, "mid_high": 1.2010, "mid_low": 1.1990, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.2001, "mid_high": 1.2012, "mid_low": 1.2000, "mid_close": 1.2011},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.2011, "mid_high": 1.2011, "mid_low": 1.2000, "mid_close": 1.2008},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.2008, "mid_high": 1.2009, "mid_low": 1.1997, "mid_close": 1.1999},
        ]
    )

    daily = module.compute_daily_metrics(bars, return_inside_bars=3, reversal_horizon_bars=4)
    summary = module.build_summary(
        daily,
        dataset_path="test.parquet",
        return_inside_bars=3,
        reversal_horizon_bars=4,
    )
    assert summary["days_analyzed"] == 1
    assert "false_break_frequency" in summary
