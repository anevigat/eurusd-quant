from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_volatility_expansion_after_compression.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("volatility_expansion_after_compression", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load volatility expansion script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_compression_and_expansion_flag() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T00:00:00Z", "mid_open": 1.1000, "mid_high": 1.1002, "mid_low": 1.0998, "mid_close": 1.1000},
            {"timestamp": "2024-01-02T06:45:00Z", "mid_open": 1.1000, "mid_high": 1.1003, "mid_low": 1.0997, "mid_close": 1.1001},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1001, "mid_high": 1.1015, "mid_low": 1.0990, "mid_close": 1.1010},
            {"timestamp": "2024-01-02T12:45:00Z", "mid_open": 1.1010, "mid_high": 1.1020, "mid_low": 1.0985, "mid_close": 1.1005},
            {"timestamp": "2024-01-02T13:00:00Z", "mid_open": 1.1005, "mid_high": 1.1010, "mid_low": 1.1000, "mid_close": 1.1008},
            {"timestamp": "2024-01-02T20:45:00Z", "mid_open": 1.1008, "mid_high": 1.1012, "mid_low": 1.1001, "mid_close": 1.1006},
        ]
    )

    daily = module.compute_daily_metrics(bars, compression_quantile=0.5)
    asia = daily[daily["session"] == "asia"].iloc[0]
    london = daily[daily["session"] == "london"].iloc[0]

    assert bool(asia["compressed_flag"]) is True
    assert asia["expansion_ratio"] > 1.0
    assert bool(asia["expansion_flag"]) is True
    assert london["next_session_range"] == pytest.approx(daily[daily["session"] == "ny"].iloc[0]["session_range"])


def test_summary_contains_expected_fields() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T00:00:00Z", "mid_open": 1.1000, "mid_high": 1.1004, "mid_low": 1.0996, "mid_close": 1.1001},
            {"timestamp": "2024-01-02T06:45:00Z", "mid_open": 1.1001, "mid_high": 1.1005, "mid_low": 1.0995, "mid_close": 1.1002},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1002, "mid_high": 1.1010, "mid_low": 1.0990, "mid_close": 1.1008},
            {"timestamp": "2024-01-02T12:45:00Z", "mid_open": 1.1008, "mid_high": 1.1012, "mid_low": 1.0988, "mid_close": 1.1006},
            {"timestamp": "2024-01-02T13:00:00Z", "mid_open": 1.1006, "mid_high": 1.1013, "mid_low": 1.1000, "mid_close": 1.1010},
            {"timestamp": "2024-01-02T20:45:00Z", "mid_open": 1.1010, "mid_high": 1.1014, "mid_low": 1.1002, "mid_close": 1.1007},
        ]
    )

    daily = module.compute_daily_metrics(bars, compression_quantile=0.25)
    summary = module.build_summary(daily, dataset_path="test.parquet", compression_quantile=0.25)
    assert "compressed_frequency" in summary
    assert "expansion_probability_after_compression" in summary
