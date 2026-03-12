from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_event_combinations.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location(
        "analyze_event_combinations", SCRIPT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load event-combination analyzer module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_test_bars(num_bars: int = 140) -> pd.DataFrame:
    ts = pd.date_range("2024-01-02 00:00:00+00:00", periods=num_bars, freq="15min")
    rows = []
    close = 1.1000
    for i, t in enumerate(ts):
        close += 0.00003
        if i in {28, 52, 76}:
            close += 0.0014
        if i in {44, 68, 92}:
            close -= 0.0015

        mid_close = close
        mid_open = mid_close - 0.00005
        mid_high = mid_close + 0.00020
        mid_low = mid_close - 0.00020
        spread = 0.00010
        half = spread / 2.0
        rows.append(
            {
                "timestamp": t,
                "symbol": "EURUSD",
                "timeframe": "15m",
                "bid_open": mid_open - half,
                "bid_high": mid_high - half,
                "bid_low": mid_low - half,
                "bid_close": mid_close - half,
                "ask_open": mid_open + half,
                "ask_high": mid_high + half,
                "ask_low": mid_low + half,
                "ask_close": mid_close + half,
                "mid_open": mid_open,
                "mid_high": mid_high,
                "mid_low": mid_low,
                "mid_close": mid_close,
                "spread_open": spread,
                "spread_high": spread,
                "spread_low": spread,
                "spread_close": spread,
                "session_label": "other",
            }
        )
    return pd.DataFrame(rows)


def test_combination_detection_same_bar() -> None:
    module = load_script_module()
    timestamps = pd.date_range("2024-01-02 00:00:00+00:00", periods=12, freq="15min")
    flags = pd.DataFrame(
        {
            "timestamp": timestamps,
            "impulse_direction": ["none"] * 12,
            "new_high_flag": [False] * 12,
            "new_low_flag": [False] * 12,
            "compression_active": [False] * 12,
            "is_london_open": [False] * 12,
            "is_new_york_open": [False] * 12,
        }
    )
    flags.at[2, "impulse_direction"] = "up"
    flags.at[2, "new_high_flag"] = True

    closes = np.linspace(1.1, 1.11, 12)
    highs = closes + 0.0002
    lows = closes - 0.0002
    atr = np.full(12, 0.0005)

    events = module.detect_combination_events(
        flags, closes, highs, lows, atr, alignment_window_bars=0
    )
    assert (events["combination_name"] == "impulse_plus_new_high").any()


def test_directional_normalization_for_combination() -> None:
    module = load_script_module()
    timestamps = pd.date_range("2024-01-02 00:00:00+00:00", periods=12, freq="15min")
    flags = pd.DataFrame(
        {
            "timestamp": timestamps,
            "impulse_direction": ["none"] * 12,
            "new_high_flag": [False] * 12,
            "new_low_flag": [False] * 12,
            "compression_active": [False] * 12,
            "is_london_open": [False] * 12,
            "is_new_york_open": [False] * 12,
        }
    )
    flags.at[1, "impulse_direction"] = "down"
    flags.at[1, "new_low_flag"] = True

    closes = np.linspace(1.1, 1.11, 12)  # rising path
    highs = closes + 0.0002
    lows = closes - 0.0002
    atr = np.full(12, 0.0005)
    events = module.detect_combination_events(
        flags, closes, highs, lows, atr, alignment_window_bars=0
    )
    row = events.loc[events["combination_name"] == "impulse_plus_new_low"].iloc[0]
    assert row["direction"] == "down"
    assert row["return_4_bars"] < 0


def test_edge_scoring() -> None:
    module = load_script_module()
    events = pd.DataFrame(
        {
            "timestamp": ["2024-01-02T00:00:00Z", "2024-01-02T00:15:00Z"],
            "combination_name": ["x", "x"],
            "direction": ["up", "up"],
            "return_1_bar": [0.1, 0.2],
            "return_4_bars": [0.2, 0.2],
            "return_8_bars": [0.3, 0.4],
            "adverse_move_4_bars": [0.5, 0.6],
            "adverse_move_8_bars": [0.7, 0.8],
        }
    )
    summary = module.build_combination_bucket_summary(events)
    assert "edge_score" in summary.columns
    expected = abs(0.2) * np.log(2)
    assert summary.iloc[0]["edge_score"] == pytest.approx(expected)


def test_output_file_creation(tmp_path: Path) -> None:
    module = load_script_module()
    bars = make_test_bars()
    bars_path = tmp_path / "bars.parquet"
    out_dir = tmp_path / "out"
    bars.to_parquet(bars_path, index=False)

    events, summary, top_edges, summary_json = module.run_analysis(
        bars_path=str(bars_path),
        output_dir=str(out_dir),
        alignment_window_bars=1,
        min_sample_size=5,
    )
    assert not events.empty
    assert not summary.empty
    assert isinstance(summary_json, dict)
    assert (out_dir / "event_combinations.csv").exists()
    assert (out_dir / "combination_bucket_summary.csv").exists()
    assert (out_dir / "top_combination_edges.csv").exists()
    assert (out_dir / "summary.json").exists()
    assert not top_edges.empty

