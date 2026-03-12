from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_double_impulse_exhaustion.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_double_impulse_exhaustion", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load double-impulse module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_double_bullish_impulse_detected() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T12:45:00Z", "mid_open": 1.1000, "mid_high": 1.1002, "mid_low": 1.0998, "mid_close": 1.1000},
            {"timestamp": "2024-01-02T13:00:00Z", "mid_open": 1.1000, "mid_high": 1.1012, "mid_low": 1.0999, "mid_close": 1.1010},
            {"timestamp": "2024-01-02T13:15:00Z", "mid_open": 1.1010, "mid_high": 1.1022, "mid_low": 1.1009, "mid_close": 1.1020},
            {"timestamp": "2024-01-02T13:30:00Z", "mid_open": 1.1020, "mid_high": 1.1022, "mid_low": 1.1014, "mid_close": 1.1016},
            {"timestamp": "2024-01-02T13:45:00Z", "mid_open": 1.1016, "mid_high": 1.1017, "mid_low": 1.1008, "mid_close": 1.1010},
            {"timestamp": "2024-01-02T14:00:00Z", "mid_open": 1.1010, "mid_high": 1.1011, "mid_low": 1.1002, "mid_close": 1.1004},
        ]
    )

    daily = module.compute_daily_metrics(
        bars,
        atr_period=1,
        impulse_atr_multiple=0.5,
        max_gap_bars=8,
        reversal_horizon_bars=4,
    )
    row = daily.iloc[0]
    assert bool(row["double_impulse_flag"]) is True
    assert row["double_impulse_direction"] == "bullish"
    assert row["reversal_ratio"] == pytest.approx((1.1020 - 1.1002) / (1.1020 - 1.1010))


def test_summary_contains_expected_fields() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T12:45:00Z", "mid_open": 1.2000, "mid_high": 1.2002, "mid_low": 1.1998, "mid_close": 1.2000},
            {"timestamp": "2024-01-02T13:00:00Z", "mid_open": 1.2000, "mid_high": 1.2012, "mid_low": 1.1999, "mid_close": 1.2010},
            {"timestamp": "2024-01-02T13:15:00Z", "mid_open": 1.2010, "mid_high": 1.2022, "mid_low": 1.2009, "mid_close": 1.2020},
            {"timestamp": "2024-01-02T13:30:00Z", "mid_open": 1.2020, "mid_high": 1.2022, "mid_low": 1.2015, "mid_close": 1.2018},
            {"timestamp": "2024-01-02T13:45:00Z", "mid_open": 1.2018, "mid_high": 1.2019, "mid_low": 1.2011, "mid_close": 1.2013},
        ]
    )

    daily = module.compute_daily_metrics(
        bars,
        atr_period=1,
        impulse_atr_multiple=0.5,
        max_gap_bars=8,
        reversal_horizon_bars=4,
    )
    summary = module.build_summary(
        daily,
        dataset_path="test.parquet",
        atr_period=1,
        impulse_atr_multiple=0.5,
        max_gap_bars=8,
        reversal_horizon_bars=4,
    )
    assert summary["days_analyzed"] == 1
    assert "double_impulse_frequency" in summary
