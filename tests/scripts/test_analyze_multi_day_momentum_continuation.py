from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_multi_day_momentum_continuation.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("multi_day_momentum", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load multi-day momentum diagnostic script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_daily_aggregation() -> None:
    module = load_script_module()
    bars = pd.DataFrame(
        [
            {
                "timestamp": "2024-01-02T00:00:00Z",
                "mid_open": 1.1000,
                "mid_high": 1.1010,
                "mid_low": 1.0990,
                "mid_close": 1.1005,
            },
            {
                "timestamp": "2024-01-02T23:45:00Z",
                "mid_open": 1.1005,
                "mid_high": 1.1030,
                "mid_low": 1.1000,
                "mid_close": 1.1020,
            },
            {
                "timestamp": "2024-01-03T00:00:00Z",
                "mid_open": 1.1020,
                "mid_high": 1.1040,
                "mid_low": 1.1010,
                "mid_close": 1.1030,
            },
            {
                "timestamp": "2024-01-03T23:45:00Z",
                "mid_open": 1.1030,
                "mid_high": 1.1050,
                "mid_low": 1.1020,
                "mid_close": 1.1040,
            },
        ]
    )
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    daily = module.aggregate_daily_bars(bars)

    row = daily.iloc[0]
    assert row["daily_open"] == pytest.approx(1.1000)
    assert row["daily_high"] == pytest.approx(1.1030)
    assert row["daily_low"] == pytest.approx(1.0990)
    assert row["daily_close"] == pytest.approx(1.1020)
    assert row["daily_return"] == pytest.approx(0.0020)


def test_daily_return_and_atr_calculation() -> None:
    module = load_script_module()
    daily = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "daily_open": [1.0, 1.2, 1.3],
            "daily_high": [1.3, 1.4, 1.5],
            "daily_low": [1.0, 1.1, 1.2],
            "daily_close": [1.2, 1.3, 1.4],
            "daily_range": [0.3, 0.3, 0.3],
            "daily_return": [0.2, 0.1, 0.1],
        }
    )
    atr = module.compute_daily_atr(daily, period=2)
    assert pd.isna(atr.iloc[0])
    assert atr.iloc[1] == pytest.approx(0.3)
    assert atr.iloc[2] == pytest.approx(0.3)


def test_strong_momentum_event_detection() -> None:
    module = load_script_module()
    rows = []
    for i in range(20):
        open_ = 1.0000 + (i * 0.0010)
        close = open_ + 0.0010
        if i == 14:
            close = open_ + 0.0060  # strong momentum day after ATR warmup
        high = max(open_, close) + 0.0010
        low = min(open_, close) - 0.0010
        rows.append(
            {
                "date": str(pd.Timestamp("2024-01-01") + pd.Timedelta(days=i))[:10],
                "daily_open": open_,
                "daily_high": high,
                "daily_low": low,
                "daily_close": close,
                "daily_range": high - low,
                "daily_return": close - open_,
            }
        )
    daily = pd.DataFrame(rows)
    events = module.compute_event_metrics(daily)
    signal_row = events.iloc[14]
    assert signal_row["direction"] == "bullish_momentum"
    assert bool(signal_row["strong_momentum_flag"]) is True


def test_continuation_calculation() -> None:
    module = load_script_module()
    rows = []
    for i in range(20):
        open_ = 1.0000 + (i * 0.0010)
        close = open_ + 0.0010
        if i == 14:
            close = 1.0200
        if i == 15:
            close = 1.0220
        if i == 16:
            close = 1.0230
        if i == 17:
            close = 1.0240
        high = max(open_, close) + 0.0010
        low = min(open_, close) - 0.0010
        rows.append(
            {
                "date": str(pd.Timestamp("2024-02-01") + pd.Timedelta(days=i))[:10],
                "daily_open": open_,
                "daily_high": high,
                "daily_low": low,
                "daily_close": close,
                "daily_range": high - low,
                "daily_return": close - open_,
            }
        )
    events = module.compute_event_metrics(pd.DataFrame(rows))
    signal_row = events.iloc[14]
    assert signal_row["continuation_1d_atr"] > 0
    assert signal_row["continuation_2d_atr"] > 0
    assert signal_row["continuation_3d_atr"] > 0


def test_output_file_creation(tmp_path: Path) -> None:
    module = load_script_module()
    events = pd.DataFrame(
        {
            "date": ["2024-01-01"],
            "direction": ["bullish_momentum"],
            "daily_open": [1.0],
            "daily_high": [1.1],
            "daily_low": [0.9],
            "daily_close": [1.05],
            "daily_range": [0.2],
            "daily_return": [0.05],
            "daily_atr": [0.04],
            "daily_return_atr": [1.25],
            "strong_momentum_flag": [True],
            "continuation_1d_atr": [0.2],
            "continuation_2d_atr": [0.3],
            "continuation_3d_atr": [0.4],
            "adverse_1d_atr": [0.1],
            "adverse_2d_atr": [0.15],
            "adverse_3d_atr": [0.2],
        }
    )
    summary = {"days_analyzed": 1, "diagnostic_verdict": "researched_but_not_promising"}
    distribution = pd.DataFrame(
        [{"metric": "daily_return_atr", "count": 1, "min": 1.25, "p50": 1.25, "max": 1.25}]
    )

    module.write_outputs(tmp_path, summary, events, distribution)

    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "daily_metrics.csv").exists()
    assert (tmp_path / "distribution.csv").exists()
    loaded = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert loaded["days_analyzed"] == 1
