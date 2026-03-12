from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_trend_exhaustion_reversal.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_trend_exhaustion_reversal", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load trend-exhaustion module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_detects_bullish_exhaustion_then_reversal() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1000, "mid_high": 1.1030, "mid_low": 1.0998, "mid_close": 1.1028},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.1028, "mid_high": 1.1030, "mid_low": 1.1024, "mid_close": 1.1026},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.1026, "mid_high": 1.1027, "mid_low": 1.0995, "mid_close": 1.0997},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_open": 1.0997, "mid_high": 1.1000, "mid_low": 1.0989, "mid_close": 1.0991},
            {"timestamp": "2024-01-02T08:00:00Z", "mid_open": 1.0991, "mid_high": 1.0994, "mid_low": 1.0986, "mid_close": 1.0989},
            {"timestamp": "2024-01-02T08:15:00Z", "mid_open": 1.0989, "mid_high": 1.0992, "mid_low": 1.0985, "mid_close": 1.0988},
        ]
    )

    daily = module.compute_daily_metrics(
        bars,
        atr_period=1,
        impulse_atr_threshold=0.5,
        slowdown_factor=0.5,
        structure_break_bars=3,
        reversal_horizon_bars=3,
    )
    row = daily.iloc[0]
    assert bool(row["exhaustion_event_flag"]) is True
    assert row["exhaustion_direction"] == "bullish"
    assert row["reversal_ratio"] == pytest.approx((1.0997 - 1.0985) / (1.1028 - 1.1000))


def test_summary_fields_present() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.2000, "mid_high": 1.2030, "mid_low": 1.1998, "mid_close": 1.2028},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.2028, "mid_high": 1.2030, "mid_low": 1.2024, "mid_close": 1.2026},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.2026, "mid_high": 1.2027, "mid_low": 1.1995, "mid_close": 1.1997},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_open": 1.1997, "mid_high": 1.2000, "mid_low": 1.1989, "mid_close": 1.1991},
            {"timestamp": "2024-01-02T08:00:00Z", "mid_open": 1.1991, "mid_high": 1.1994, "mid_low": 1.1986, "mid_close": 1.1989},
            {"timestamp": "2024-01-02T08:15:00Z", "mid_open": 1.1989, "mid_high": 1.1992, "mid_low": 1.1985, "mid_close": 1.1988},
        ]
    )

    daily = module.compute_daily_metrics(
        bars,
        atr_period=1,
        impulse_atr_threshold=0.5,
        slowdown_factor=0.5,
        structure_break_bars=3,
        reversal_horizon_bars=3,
    )
    summary = module.build_summary(
        daily,
        dataset_path="test.parquet",
        atr_period=1,
        impulse_atr_threshold=0.5,
        slowdown_factor=0.5,
        structure_break_bars=3,
        reversal_horizon_bars=3,
    )
    assert summary["days_analyzed"] == 1
    assert "exhaustion_event_frequency" in summary
