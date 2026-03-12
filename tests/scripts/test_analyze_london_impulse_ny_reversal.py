from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_london_impulse_ny_reversal.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_london_impulse_ny_reversal", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load london-impulse-ny-reversal module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_bullish_london_impulse_reversal_ratio() -> None:
    module = load_script_module()
    rows = []
    for i in range(20):
        ts = pd.Timestamp("2024-01-02T00:00:00Z") + pd.Timedelta(minutes=15 * i)
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "mid_open": 1.1000,
                "mid_high": 1.1003,
                "mid_low": 1.0997,
                "mid_close": 1.1000,
            }
        )
    rows.extend(
        [
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1000, "mid_high": 1.1010, "mid_low": 1.0998, "mid_close": 1.1004},
            {"timestamp": "2024-01-02T11:45:00Z", "mid_open": 1.1012, "mid_high": 1.1022, "mid_low": 1.1010, "mid_close": 1.1020},
            {"timestamp": "2024-01-02T12:00:00Z", "mid_open": 1.1020, "mid_high": 1.1021, "mid_low": 1.1009, "mid_close": 1.1015},
            {"timestamp": "2024-01-02T15:45:00Z", "mid_open": 1.1016, "mid_high": 1.1026, "mid_low": 1.1008, "mid_close": 1.1021},
        ]
    )
    bars = make_bars(rows)

    daily = module.compute_daily_metrics(bars, strong_impulse_atr_multiple=0.2)
    row = daily.iloc[0]
    assert row["impulse_direction"] == "bullish"
    assert bool(row["strong_london_impulse_flag"]) is True
    assert row["reversal_ratio"] == pytest.approx((1.1020 - 1.1008) / (1.1020 - 1.1000))
    assert row["adverse_move_ratio"] == pytest.approx((1.1026 - 1.1020) / (1.1020 - 1.1000))


def test_summary_fields_present() -> None:
    module = load_script_module()
    rows = []
    for i in range(20):
        ts = pd.Timestamp("2024-01-03T00:00:00Z") + pd.Timedelta(minutes=15 * i)
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "mid_open": 1.2000,
                "mid_high": 1.2004,
                "mid_low": 1.1996,
                "mid_close": 1.2001,
            }
        )
    rows.extend(
        [
            {"timestamp": "2024-01-03T07:00:00Z", "mid_open": 1.2001, "mid_high": 1.2015, "mid_low": 1.2000, "mid_close": 1.2010},
            {"timestamp": "2024-01-03T11:45:00Z", "mid_open": 1.2010, "mid_high": 1.2020, "mid_low": 1.2008, "mid_close": 1.2018},
            {"timestamp": "2024-01-03T12:00:00Z", "mid_open": 1.2018, "mid_high": 1.2020, "mid_low": 1.2010, "mid_close": 1.2012},
            {"timestamp": "2024-01-03T15:45:00Z", "mid_open": 1.2012, "mid_high": 1.2022, "mid_low": 1.2009, "mid_close": 1.2014},
        ]
    )
    bars = make_bars(rows)

    daily = module.compute_daily_metrics(bars, strong_impulse_atr_multiple=0.2)
    summary = module.build_summary(daily, dataset_path="test.parquet", strong_impulse_atr_multiple=0.2)
    assert summary["days_analyzed"] == 1
    assert "median_reversal_ratio" in summary
