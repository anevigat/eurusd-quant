from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_cup_handle_breakout.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_cup_handle_breakout", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load cup-handle module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_detects_cup_handle_breakout() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1050, "mid_high": 1.1060, "mid_low": 1.1040, "mid_close": 1.1055},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.1055, "mid_high": 1.1100, "mid_low": 1.1050, "mid_close": 1.1090},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.1090, "mid_high": 1.1080, "mid_low": 1.1030, "mid_close": 1.1040},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_open": 1.1040, "mid_high": 1.1060, "mid_low": 1.1010, "mid_close": 1.1020},
            {"timestamp": "2024-01-02T08:00:00Z", "mid_open": 1.1020, "mid_high": 1.1040, "mid_low": 1.1000, "mid_close": 1.1030},
            {"timestamp": "2024-01-02T08:15:00Z", "mid_open": 1.1030, "mid_high": 1.1060, "mid_low": 1.1020, "mid_close": 1.1050},
            {"timestamp": "2024-01-02T08:30:00Z", "mid_open": 1.1050, "mid_high": 1.1080, "mid_low": 1.1040, "mid_close": 1.1070},
            {"timestamp": "2024-01-02T08:45:00Z", "mid_open": 1.1070, "mid_high": 1.1095, "mid_low": 1.1060, "mid_close": 1.1090},
            {"timestamp": "2024-01-02T09:00:00Z", "mid_open": 1.1090, "mid_high": 1.1092, "mid_low": 1.1065, "mid_close": 1.1072},
            {"timestamp": "2024-01-02T09:15:00Z", "mid_open": 1.1072, "mid_high": 1.1112, "mid_low": 1.1070, "mid_close": 1.1110},
            {"timestamp": "2024-01-02T09:30:00Z", "mid_open": 1.1110, "mid_high": 1.1140, "mid_low": 1.1100, "mid_close": 1.1130},
            {"timestamp": "2024-01-02T09:45:00Z", "mid_open": 1.1130, "mid_high": 1.1138, "mid_low": 1.1105, "mid_close": 1.1110},
        ]
    )

    daily = module.compute_daily_metrics(
        bars,
        atr_period=1,
        min_cup_depth_atr=0.5,
        rim_tolerance_atr=0.5,
        max_handle_depth_ratio=0.6,
        handle_max_bars=6,
        follow_horizon_bars=2,
    )
    row = daily.iloc[0]
    assert bool(row["pattern_flag"]) is True
    assert float(row["breakout_follow_through_ratio"]) > 0.0


def test_summary_fields_present() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.2000, "mid_high": 1.2004, "mid_low": 1.1998, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.2001, "mid_high": 1.2005, "mid_low": 1.1998, "mid_close": 1.2000},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.2000, "mid_high": 1.2003, "mid_low": 1.1997, "mid_close": 1.1999},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_open": 1.1999, "mid_high": 1.2003, "mid_low": 1.1997, "mid_close": 1.2000},
            {"timestamp": "2024-01-02T08:00:00Z", "mid_open": 1.2000, "mid_high": 1.2004, "mid_low": 1.1998, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T08:15:00Z", "mid_open": 1.2001, "mid_high": 1.2004, "mid_low": 1.1998, "mid_close": 1.2000},
            {"timestamp": "2024-01-02T08:30:00Z", "mid_open": 1.2000, "mid_high": 1.2003, "mid_low": 1.1999, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T08:45:00Z", "mid_open": 1.2001, "mid_high": 1.2003, "mid_low": 1.1999, "mid_close": 1.2000},
            {"timestamp": "2024-01-02T09:00:00Z", "mid_open": 1.2000, "mid_high": 1.2003, "mid_low": 1.1999, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T09:15:00Z", "mid_open": 1.2001, "mid_high": 1.2004, "mid_low": 1.1999, "mid_close": 1.2000},
            {"timestamp": "2024-01-02T09:30:00Z", "mid_open": 1.2000, "mid_high": 1.2003, "mid_low": 1.1999, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T09:45:00Z", "mid_open": 1.2001, "mid_high": 1.2004, "mid_low": 1.1999, "mid_close": 1.2000},
        ]
    )

    daily = module.compute_daily_metrics(
        bars,
        atr_period=1,
        min_cup_depth_atr=0.5,
        rim_tolerance_atr=0.5,
        max_handle_depth_ratio=0.6,
        handle_max_bars=6,
        follow_horizon_bars=2,
    )
    summary = module.build_summary(
        daily,
        dataset_path="test.parquet",
        atr_period=1,
        min_cup_depth_atr=0.5,
        rim_tolerance_atr=0.5,
        max_handle_depth_ratio=0.6,
        handle_max_bars=6,
        follow_horizon_bars=2,
    )
    assert summary["days_analyzed"] == 1
    assert "pattern_frequency" in summary

