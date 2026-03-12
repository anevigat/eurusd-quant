from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_break_retest_continuation.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_break_retest_continuation", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load break-retest script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_detects_break_retest_and_continuation() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T00:00:00Z", "mid_open": 1.1000, "mid_high": 1.1010, "mid_low": 1.0990, "mid_close": 1.1000},
            {"timestamp": "2024-01-02T06:45:00Z", "mid_open": 1.1000, "mid_high": 1.1010, "mid_low": 1.0990, "mid_close": 1.1002},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1002, "mid_high": 1.1015, "mid_low": 1.1000, "mid_close": 1.1012},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.1012, "mid_high": 1.1013, "mid_low": 1.1008, "mid_close": 1.1011},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.1011, "mid_high": 1.1020, "mid_low": 1.1007, "mid_close": 1.1018},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_open": 1.1018, "mid_high": 1.1022, "mid_low": 1.1010, "mid_close": 1.1019},
            {"timestamp": "2024-01-02T08:00:00Z", "mid_open": 1.1019, "mid_high": 1.1024, "mid_low": 1.1012, "mid_close": 1.1021},
            {"timestamp": "2024-01-02T09:45:00Z", "mid_open": 1.1021, "mid_high": 1.1023, "mid_low": 1.1016, "mid_close": 1.1019},
        ]
    )

    daily = module.compute_daily_metrics(bars)
    row = daily.iloc[0]
    assert bool(row["breakout_flag"]) is True
    assert row["breakout_direction"] == "up"
    assert bool(row["retest_flag"]) is True
    assert row["follow_through_R"] == pytest.approx(0.70, abs=1e-8)
    assert row["adverse_move_R"] == pytest.approx(0.15, abs=1e-8)
    assert bool(row["continuation_win_flag"]) is True


def test_summary_fields_present() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-03T00:00:00Z", "mid_open": 1.2000, "mid_high": 1.2010, "mid_low": 1.1990, "mid_close": 1.2001},
            {"timestamp": "2024-01-03T06:45:00Z", "mid_open": 1.2001, "mid_high": 1.2010, "mid_low": 1.1990, "mid_close": 1.2000},
            {"timestamp": "2024-01-03T07:00:00Z", "mid_open": 1.2000, "mid_high": 1.2008, "mid_low": 1.1986, "mid_close": 1.1988},
            {"timestamp": "2024-01-03T07:15:00Z", "mid_open": 1.1988, "mid_high": 1.1994, "mid_low": 1.1987, "mid_close": 1.1992},
            {"timestamp": "2024-01-03T08:30:00Z", "mid_open": 1.1992, "mid_high": 1.1994, "mid_low": 1.1980, "mid_close": 1.1983},
            {"timestamp": "2024-01-03T09:45:00Z", "mid_open": 1.1983, "mid_high": 1.1986, "mid_low": 1.1978, "mid_close": 1.1982},
        ]
    )

    daily = module.compute_daily_metrics(bars)
    summary = module.build_summary(daily, dataset_path="test.parquet")
    assert summary["days_analyzed"] == 1
    assert "retest_frequency_on_breakouts" in summary
    assert "median_follow_through_R_after_retest" in summary
