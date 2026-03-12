from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_liquidity_sweep_reversal.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_liquidity_sweep_reversal", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load liquidity sweep script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_sweep_up_then_return_inside_detected() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-01T10:00:00Z", "mid_open": 1.1000, "mid_high": 1.1010, "mid_low": 1.0990, "mid_close": 1.1000},
            {"timestamp": "2024-01-01T16:45:00Z", "mid_open": 1.1000, "mid_high": 1.1010, "mid_low": 1.0990, "mid_close": 1.1002},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1002, "mid_high": 1.1012, "mid_low": 1.1000, "mid_close": 1.1011},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.1011, "mid_high": 1.1012, "mid_low": 1.0998, "mid_close": 1.1008},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.1008, "mid_high": 1.1009, "mid_low": 1.0997, "mid_close": 1.1000},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_open": 1.1000, "mid_high": 1.1003, "mid_low": 1.0994, "mid_close": 1.0997},
            {"timestamp": "2024-01-02T08:00:00Z", "mid_open": 1.0997, "mid_high": 1.1004, "mid_low": 1.0996, "mid_close": 1.1002},
        ]
    )

    daily = module.compute_daily_metrics(bars, return_inside_bars=4, reversal_horizon_bars=4)
    row = daily.iloc[0]
    assert bool(row["sweep_flag"]) is True
    assert row["sweep_direction"] == "sweep_up"
    assert row["follow_through_R"] == pytest.approx((1.1008 - 1.0994) / (1.1010 - 1.0990))


def test_summary_fields_present() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-01T10:00:00Z", "mid_open": 1.2000, "mid_high": 1.2010, "mid_low": 1.1990, "mid_close": 1.2002},
            {"timestamp": "2024-01-01T16:45:00Z", "mid_open": 1.2002, "mid_high": 1.2010, "mid_low": 1.1990, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.2001, "mid_high": 1.2011, "mid_low": 1.2000, "mid_close": 1.2010},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.2010, "mid_high": 1.2012, "mid_low": 1.1998, "mid_close": 1.2008},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.2008, "mid_high": 1.2009, "mid_low": 1.1996, "mid_close": 1.2000},
        ]
    )

    daily = module.compute_daily_metrics(bars, return_inside_bars=4, reversal_horizon_bars=4)
    summary = module.build_summary(
        daily,
        dataset_path="test.parquet",
        return_inside_bars=4,
        reversal_horizon_bars=4,
    )
    assert summary["days_analyzed"] == 1
    assert "reversal_probability" in summary
