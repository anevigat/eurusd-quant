from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_filtered_london_breakout.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("filtered_london_breakout", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load filtered London breakout diagnostic script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_bars(rows: list[dict[str, float | str]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def test_asian_range_calculation() -> None:
    module = load_script_module()
    bars = _make_bars(
        [
            {"timestamp": "2024-01-02T00:00:00Z", "mid_open": 1.1000, "mid_high": 1.1020, "mid_low": 1.0990, "mid_close": 1.1010},
            {"timestamp": "2024-01-02T06:45:00Z", "mid_open": 1.1010, "mid_high": 1.1030, "mid_low": 1.0980, "mid_close": 1.1020},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1020, "mid_high": 1.1040, "mid_low": 1.1010, "mid_close": 1.1035},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.1035, "mid_high": 1.1050, "mid_low": 1.1020, "mid_close": 1.1040},
        ]
    )
    daily = module.compute_daily_metrics(bars)
    row = daily.iloc[0]
    assert row["asian_high"] == pytest.approx(1.1030)
    assert row["asian_low"] == pytest.approx(1.0980)
    assert row["asian_range"] == pytest.approx(0.0050)


def test_compression_flag_assignment() -> None:
    module = load_script_module()
    daily = pd.DataFrame(
        {
            "asian_range_atr_ratio": [1.0, 2.0, 3.0, 4.0],
            "compressed_day_flag": [False, False, False, False],
        }
    )
    flagged, q = module.assign_compression_flag(daily)
    assert q["p25"] == pytest.approx(1.75)
    assert bool(flagged.iloc[0]["compressed_day_flag"]) is True
    assert bool(flagged.iloc[1]["compressed_day_flag"]) is False


def test_confirmed_breakout_by_close_logic() -> None:
    module = load_script_module()
    london = _make_bars(
        [
            {"timestamp": "2024-01-02T07:00:00Z", "mid_high": 1.1010, "mid_low": 1.0990, "mid_close": 1.1000},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_high": 1.1020, "mid_low": 1.1000, "mid_close": 1.1015},  # upside close confirm
            {"timestamp": "2024-01-02T07:30:00Z", "mid_high": 1.1025, "mid_low": 1.0980, "mid_close": 1.0985},  # downside confirm later
        ]
    )
    confirmed, direction, break_time, breakout_close = module.detect_confirmed_breakout_by_close(
        london=london,
        asian_high=1.1010,
        asian_low=1.0990,
    )
    assert confirmed is True
    assert direction == "upside"
    assert str(break_time) == "2024-01-02 07:15:00+00:00"
    assert breakout_close == pytest.approx(1.1015)


def test_follow_through_adverse_calculation() -> None:
    module = load_script_module()
    london = _make_bars(
        [
            {"timestamp": "2024-01-02T07:15:00Z", "mid_high": 1.1020, "mid_low": 1.1000, "mid_close": 1.1015},
            {"timestamp": "2024-01-02T07:30:00Z", "mid_high": 1.1030, "mid_low": 1.1005, "mid_close": 1.1020},
            {"timestamp": "2024-01-02T07:45:00Z", "mid_high": 1.1028, "mid_low": 1.0998, "mid_close": 1.1002},
        ]
    )
    follow, adverse = module.compute_follow_and_adverse_after_confirmation(
        london=london,
        confirmed_break_direction="upside",
        confirmed_break_time=pd.Timestamp("2024-01-02T07:15:00Z"),
        breakout_close=1.1015,
    )
    assert follow == pytest.approx(0.0015)
    assert adverse == pytest.approx(0.0017)


def test_output_file_creation(tmp_path: Path) -> None:
    module = load_script_module()
    summary = {"days_analyzed": 1, "diagnostic_verdict": "researched_but_not_promising"}
    daily = pd.DataFrame(
        [
            {
                "date": "2024-01-02",
                "asian_range": 0.0040,
                "atr": 0.0010,
                "asian_range_atr_ratio": 4.0,
                "compressed_day_flag": True,
                "confirmed_breakout_flag": True,
                "confirmed_break_direction": "upside",
                "confirmed_break_time": "2024-01-02T07:15:00+00:00",
                "follow_through_R": 0.4,
                "adverse_move_R": 0.2,
            }
        ]
    )
    distribution = pd.DataFrame([{"section": "x", "metric": "y", "value": 1.0}])

    module.write_outputs(tmp_path, summary, daily, distribution)

    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "daily_metrics.csv").exists()
    assert (tmp_path / "distribution.csv").exists()
    loaded = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert loaded["days_analyzed"] == 1
