from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_double_top_bottom.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_double_top_bottom", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load double-top-bottom module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_detects_double_top_and_neckline_break() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1002, "mid_high": 1.1005, "mid_low": 1.1000, "mid_close": 1.1004},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.1004, "mid_high": 1.1012, "mid_low": 1.1006, "mid_close": 1.1010},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.1010, "mid_high": 1.1008, "mid_low": 1.0998, "mid_close": 1.1000},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_open": 1.1000, "mid_high": 1.1011, "mid_low": 1.1004, "mid_close": 1.1009},
            {"timestamp": "2024-01-02T08:00:00Z", "mid_open": 1.1009, "mid_high": 1.1007, "mid_low": 1.0995, "mid_close": 1.0996},
            {"timestamp": "2024-01-02T08:15:00Z", "mid_open": 1.0996, "mid_high": 1.1002, "mid_low": 1.0990, "mid_close": 1.0992},
            {"timestamp": "2024-01-02T08:30:00Z", "mid_open": 1.0992, "mid_high": 1.0998, "mid_low": 1.0988, "mid_close": 1.0990},
            {"timestamp": "2024-01-02T08:45:00Z", "mid_open": 1.0990, "mid_high": 1.0994, "mid_low": 1.0989, "mid_close": 1.0991},
        ]
    )

    daily = module.compute_daily_metrics(
        bars,
        atr_period=1,
        peak_tolerance_atr=0.5,
        min_pullback_atr=0.2,
        reversal_horizon_bars=3,
    )
    row = daily.iloc[0]
    assert bool(row["pattern_flag"]) is True
    assert row["pattern_type"] == "double_top"
    assert row["follow_through_R"] > row["adverse_move_R"]


def test_summary_contains_expected_fields() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.2002, "mid_high": 1.2005, "mid_low": 1.2000, "mid_close": 1.2004},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.2004, "mid_high": 1.2012, "mid_low": 1.2006, "mid_close": 1.2010},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.2010, "mid_high": 1.2008, "mid_low": 1.1998, "mid_close": 1.2000},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_open": 1.2000, "mid_high": 1.2011, "mid_low": 1.2004, "mid_close": 1.2009},
            {"timestamp": "2024-01-02T08:00:00Z", "mid_open": 1.2009, "mid_high": 1.2007, "mid_low": 1.1995, "mid_close": 1.1996},
            {"timestamp": "2024-01-02T08:15:00Z", "mid_open": 1.1996, "mid_high": 1.2002, "mid_low": 1.1990, "mid_close": 1.1992},
            {"timestamp": "2024-01-02T08:30:00Z", "mid_open": 1.1992, "mid_high": 1.1998, "mid_low": 1.1988, "mid_close": 1.1990},
            {"timestamp": "2024-01-02T08:45:00Z", "mid_open": 1.1990, "mid_high": 1.1994, "mid_low": 1.1989, "mid_close": 1.1991},
        ]
    )

    daily = module.compute_daily_metrics(
        bars,
        atr_period=1,
        peak_tolerance_atr=0.5,
        min_pullback_atr=0.2,
        reversal_horizon_bars=3,
    )
    summary = module.build_summary(
        daily,
        dataset_path="test.parquet",
        atr_period=1,
        peak_tolerance_atr=0.5,
        min_pullback_atr=0.2,
        reversal_horizon_bars=3,
    )
    assert summary["days_analyzed"] == 1
    assert "pattern_frequency" in summary
    assert summary["reversal_probability"] == pytest.approx(1.0)
