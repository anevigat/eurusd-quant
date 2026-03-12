from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_session_vwap_reversion.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_session_vwap_reversion", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load session VWAP reversion module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_observations_have_session_vwap_deviation_and_reversion() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T06:45:00Z", "mid_open": 1.1000, "mid_high": 1.1004, "mid_low": 1.0996, "mid_close": 1.1000},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1000, "mid_high": 1.1020, "mid_low": 1.0990, "mid_close": 1.1018},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.1018, "mid_high": 1.1022, "mid_low": 1.1008, "mid_close": 1.1010},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.1010, "mid_high": 1.1012, "mid_low": 1.1000, "mid_close": 1.1003},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_open": 1.1003, "mid_high": 1.1008, "mid_low": 1.0998, "mid_close": 1.1000},
            {"timestamp": "2024-01-02T08:00:00Z", "mid_open": 1.1000, "mid_high": 1.1004, "mid_low": 1.0997, "mid_close": 1.0999},
            {"timestamp": "2024-01-02T08:15:00Z", "mid_open": 1.0999, "mid_high": 1.1002, "mid_low": 1.0996, "mid_close": 1.0998},
            {"timestamp": "2024-01-02T08:30:00Z", "mid_open": 1.0998, "mid_high": 1.1000, "mid_low": 1.0995, "mid_close": 1.0997},
            {"timestamp": "2024-01-02T08:45:00Z", "mid_open": 1.0997, "mid_high": 1.0999, "mid_low": 1.0994, "mid_close": 1.0996},
            {"timestamp": "2024-01-02T09:00:00Z", "mid_open": 1.0996, "mid_high": 1.0998, "mid_low": 1.0993, "mid_close": 1.0995},
        ]
    )

    obs = module.compute_observations(bars, atr_period=1)
    assert not obs.empty
    assert "deviation_atr" in obs.columns
    assert "reversion_ratio_4bars" in obs.columns


def test_summary_contains_bucket_and_session_stats() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T06:45:00Z", "mid_open": 1.2000, "mid_high": 1.2004, "mid_low": 1.1996, "mid_close": 1.2000},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.2000, "mid_high": 1.2020, "mid_low": 1.1990, "mid_close": 1.2018},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.2018, "mid_high": 1.2022, "mid_low": 1.2008, "mid_close": 1.2010},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_open": 1.2010, "mid_high": 1.2012, "mid_low": 1.2000, "mid_close": 1.2003},
            {"timestamp": "2024-01-02T12:00:00Z", "mid_open": 1.2003, "mid_high": 1.2015, "mid_low": 1.1998, "mid_close": 1.2010},
            {"timestamp": "2024-01-02T12:15:00Z", "mid_open": 1.2010, "mid_high": 1.2012, "mid_low": 1.2002, "mid_close": 1.2004},
            {"timestamp": "2024-01-02T12:30:00Z", "mid_open": 1.2004, "mid_high": 1.2008, "mid_low": 1.1999, "mid_close": 1.2001},
            {"timestamp": "2024-01-02T12:45:00Z", "mid_open": 1.2001, "mid_high": 1.2004, "mid_low": 1.1997, "mid_close": 1.1999},
            {"timestamp": "2024-01-02T13:00:00Z", "mid_open": 1.1999, "mid_high": 1.2002, "mid_low": 1.1995, "mid_close": 1.1998},
            {"timestamp": "2024-01-02T13:15:00Z", "mid_open": 1.1998, "mid_high": 1.2000, "mid_low": 1.1994, "mid_close": 1.1997},
            {"timestamp": "2024-01-02T13:30:00Z", "mid_open": 1.1997, "mid_high": 1.1999, "mid_low": 1.1993, "mid_close": 1.1996},
            {"timestamp": "2024-01-02T13:45:00Z", "mid_open": 1.1996, "mid_high": 1.1998, "mid_low": 1.1992, "mid_close": 1.1995},
            {"timestamp": "2024-01-02T14:00:00Z", "mid_open": 1.1995, "mid_high": 1.1997, "mid_low": 1.1991, "mid_close": 1.1994},
            {"timestamp": "2024-01-02T14:15:00Z", "mid_open": 1.1994, "mid_high": 1.1996, "mid_low": 1.1990, "mid_close": 1.1993},
            {"timestamp": "2024-01-02T14:30:00Z", "mid_open": 1.1993, "mid_high": 1.1995, "mid_low": 1.1989, "mid_close": 1.1992},
            {"timestamp": "2024-01-02T14:45:00Z", "mid_open": 1.1992, "mid_high": 1.1994, "mid_low": 1.1988, "mid_close": 1.1991},
        ]
    )

    obs = module.compute_observations(bars, atr_period=1)
    obs, cutoffs = module.assign_buckets(obs)
    summary = module.build_summary(obs, dataset_path="test.parquet", atr_period=1, bucket_cutoffs=cutoffs)
    assert summary["bars_analyzed"] > 0
    assert "deviation_bucket_stats" in summary
    assert "session_stats" in summary
