from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "analyze_session_liquidity_sweep_reversal.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("session_liquidity_sweep_reversal", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load session liquidity sweep reversal script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_sweep_above_reversal_metrics() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T00:00:00Z", "mid_high": 1.1020, "mid_low": 1.1000, "mid_open": 1.1010, "mid_close": 1.1015},
            {"timestamp": "2024-01-02T06:45:00Z", "mid_high": 1.1030, "mid_low": 1.0990, "mid_open": 1.1015, "mid_close": 1.1005},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_high": 1.1032, "mid_low": 1.1010, "mid_open": 1.1005, "mid_close": 1.1025},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_high": 1.1040, "mid_low": 1.1005, "mid_open": 1.1025, "mid_close": 1.1010},
        ]
    )

    daily = module.compute_daily_metrics(bars)
    row = daily.iloc[0]
    assert bool(row["sweep_detected"]) is True
    assert row["sweep_direction"] == "above"
    assert row["reversal_move"] == pytest.approx(0.0025)
    assert row["continuation_move"] == pytest.approx(0.0010)


def test_no_sweep_day_classified_none() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-03T00:00:00Z", "mid_high": 1.2020, "mid_low": 1.2000, "mid_open": 1.2010, "mid_close": 1.2015},
            {"timestamp": "2024-01-03T06:45:00Z", "mid_high": 1.2030, "mid_low": 1.1990, "mid_open": 1.2015, "mid_close": 1.2005},
            {"timestamp": "2024-01-03T07:00:00Z", "mid_high": 1.2025, "mid_low": 1.1995, "mid_open": 1.2005, "mid_close": 1.2010},
            {"timestamp": "2024-01-03T07:15:00Z", "mid_high": 1.2028, "mid_low": 1.1992, "mid_open": 1.2010, "mid_close": 1.2008},
        ]
    )

    daily = module.compute_daily_metrics(bars)
    row = daily.iloc[0]
    assert bool(row["sweep_detected"]) is False
    assert row["sweep_direction"] == "none"
