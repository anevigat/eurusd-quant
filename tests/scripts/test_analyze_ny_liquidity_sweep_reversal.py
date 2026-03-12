from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "analyze_ny_liquidity_sweep_reversal.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("ny_liquidity_sweep_reversal", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load ny liquidity sweep reversal script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_ny_sweep_above_reversal() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T07:00:00Z", "mid_high": 1.1020, "mid_low": 1.1000, "mid_open": 1.1010, "mid_close": 1.1012},
            {"timestamp": "2024-01-02T12:45:00Z", "mid_high": 1.1030, "mid_low": 1.0990, "mid_open": 1.1012, "mid_close": 1.1008},
            {"timestamp": "2024-01-02T13:00:00Z", "mid_high": 1.1035, "mid_low": 1.1010, "mid_open": 1.1008, "mid_close": 1.1020},
            {"timestamp": "2024-01-02T13:15:00Z", "mid_high": 1.1040, "mid_low": 1.1005, "mid_open": 1.1020, "mid_close": 1.1010},
        ]
    )

    daily = module.compute_daily_metrics(bars)
    row = daily.iloc[0]
    assert bool(row["sweep_detected"]) is True
    assert row["sweep_direction"] == "above"
    assert row["reversal_move"] == pytest.approx(0.0025)
    assert row["continuation_move"] == pytest.approx(0.0010)


def test_no_ny_sweep_day() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-03T07:00:00Z", "mid_high": 1.2020, "mid_low": 1.2000, "mid_open": 1.2010, "mid_close": 1.2012},
            {"timestamp": "2024-01-03T12:45:00Z", "mid_high": 1.2030, "mid_low": 1.1990, "mid_open": 1.2012, "mid_close": 1.2008},
            {"timestamp": "2024-01-03T13:00:00Z", "mid_high": 1.2028, "mid_low": 1.1992, "mid_open": 1.2008, "mid_close": 1.2009},
            {"timestamp": "2024-01-03T13:15:00Z", "mid_high": 1.2029, "mid_low": 1.1991, "mid_open": 1.2009, "mid_close": 1.2007},
        ]
    )

    daily = module.compute_daily_metrics(bars)
    row = daily.iloc[0]
    assert bool(row["sweep_detected"]) is False
    assert row["sweep_direction"] == "none"
