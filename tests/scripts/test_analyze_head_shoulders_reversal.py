from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_head_shoulders_reversal.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_head_shoulders_reversal", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load head-and-shoulders module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_detects_bearish_head_shoulders_break() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1000, "mid_high": 1.1020, "mid_low": 1.0995, "mid_close": 1.1015},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.1015, "mid_high": 1.1080, "mid_low": 1.1010, "mid_close": 1.1070},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.1070, "mid_high": 1.1040, "mid_low": 1.1000, "mid_close": 1.1020},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_open": 1.1020, "mid_high": 1.1060, "mid_low": 1.1010, "mid_close": 1.1050},
            {"timestamp": "2024-01-02T08:00:00Z", "mid_open": 1.1050, "mid_high": 1.1120, "mid_low": 1.1040, "mid_close": 1.1110},
            {"timestamp": "2024-01-02T08:15:00Z", "mid_open": 1.1110, "mid_high": 1.1060, "mid_low": 1.1000, "mid_close": 1.1010},
            {"timestamp": "2024-01-02T08:30:00Z", "mid_open": 1.1010, "mid_high": 1.1090, "mid_low": 1.1030, "mid_close": 1.1080},
            {"timestamp": "2024-01-02T08:45:00Z", "mid_open": 1.1080, "mid_high": 1.1030, "mid_low": 1.0970, "mid_close": 1.0980},
            {"timestamp": "2024-01-02T09:00:00Z", "mid_open": 1.0980, "mid_high": 1.1020, "mid_low": 1.0960, "mid_close": 1.0970},
            {"timestamp": "2024-01-02T09:15:00Z", "mid_open": 1.0970, "mid_high": 1.1010, "mid_low": 1.0950, "mid_close": 1.0960},
            {"timestamp": "2024-01-02T09:30:00Z", "mid_open": 1.0960, "mid_high": 1.1000, "mid_low": 1.0955, "mid_close": 1.0965},
        ]
    )

    daily = module.compute_daily_metrics(
        bars,
        atr_period=1,
        shoulder_tolerance_atr=0.4,
        min_head_lift_atr=0.2,
        reversal_horizon_bars=3,
    )
    row = daily.iloc[0]
    assert bool(row["pattern_flag"]) is True
    assert row["pattern_type"] == "head_shoulders"
    assert float(row["follow_through_R"]) > 0.0


def test_summary_fields_present() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.2000, "mid_high": 1.2005, "mid_low": 1.1995, "mid_close": 1.2002},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.2002, "mid_high": 1.2006, "mid_low": 1.1996, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.2001, "mid_high": 1.2007, "mid_low": 1.1997, "mid_close": 1.2002},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_open": 1.2002, "mid_high": 1.2006, "mid_low": 1.1998, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T08:00:00Z", "mid_open": 1.2001, "mid_high": 1.2005, "mid_low": 1.1997, "mid_close": 1.2000},
            {"timestamp": "2024-01-02T08:15:00Z", "mid_open": 1.2000, "mid_high": 1.2004, "mid_low": 1.1997, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T08:30:00Z", "mid_open": 1.2001, "mid_high": 1.2005, "mid_low": 1.1998, "mid_close": 1.2000},
            {"timestamp": "2024-01-02T08:45:00Z", "mid_open": 1.2000, "mid_high": 1.2004, "mid_low": 1.1998, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T09:00:00Z", "mid_open": 1.2001, "mid_high": 1.2005, "mid_low": 1.1999, "mid_close": 1.2000},
            {"timestamp": "2024-01-02T09:15:00Z", "mid_open": 1.2000, "mid_high": 1.2004, "mid_low": 1.1999, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T09:30:00Z", "mid_open": 1.2001, "mid_high": 1.2004, "mid_low": 1.1999, "mid_close": 1.2000},
        ]
    )

    daily = module.compute_daily_metrics(
        bars,
        atr_period=1,
        shoulder_tolerance_atr=0.4,
        min_head_lift_atr=0.2,
        reversal_horizon_bars=3,
    )
    summary = module.build_summary(
        daily,
        dataset_path="test.parquet",
        atr_period=1,
        shoulder_tolerance_atr=0.4,
        min_head_lift_atr=0.2,
        reversal_horizon_bars=3,
    )
    assert summary["days_analyzed"] == 1
    assert "pattern_frequency" in summary

