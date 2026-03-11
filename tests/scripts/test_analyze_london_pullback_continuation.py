from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_london_pullback_continuation.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("london_pullback_refined", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load london pullback continuation script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_test_bars() -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []

    # Add pre-history bars so ATR(14) is available by London impulse.
    for i in range(16):
        ts = pd.Timestamp("2024-01-02T03:00:00Z") + pd.Timedelta(minutes=15 * i)
        base = 1.0950 + (i * 0.0002)
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "mid_open": base,
                "mid_high": base + 0.0004,
                "mid_low": base - 0.0003,
                "mid_close": base + 0.0001,
            }
        )

    # Bullish day calculations.
    rows.extend(
        [
            {
                "timestamp": "2024-01-02T07:00:00Z",
                "mid_open": 1.1000,
                "mid_high": 1.1012,
                "mid_low": 1.0998,
                "mid_close": 1.1010,
            },
            {
                "timestamp": "2024-01-02T07:15:00Z",
                "mid_open": 1.1010,
                "mid_high": 1.1022,
                "mid_low": 1.1008,
                "mid_close": 1.1020,
            },
            {
                "timestamp": "2024-01-02T07:30:00Z",
                "mid_open": 1.1020,
                "mid_high": 1.1034,
                "mid_low": 1.1017,
                "mid_close": 1.1030,
            },
            {
                "timestamp": "2024-01-02T07:45:00Z",
                "mid_open": 1.1030,
                "mid_high": 1.1032,
                "mid_low": 1.1024,
                "mid_close": 1.1028,
            },
            {
                "timestamp": "2024-01-02T08:00:00Z",
                "mid_open": 1.1028,
                "mid_high": 1.1030,
                "mid_low": 1.1020,
                "mid_close": 1.1026,
            },
            {
                "timestamp": "2024-01-02T09:00:00Z",
                "mid_open": 1.1026,
                "mid_high": 1.1042,
                "mid_low": 1.1025,
                "mid_close": 1.1038,
            },
            {
                "timestamp": "2024-01-02T09:15:00Z",
                "mid_open": 1.1038,
                "mid_high": 1.1040,
                "mid_low": 1.1034,
                "mid_close": 1.1036,
            },
        ]
    )

    # Add pre-history bars for second day.
    for i in range(16):
        ts = pd.Timestamp("2024-01-03T03:00:00Z") + pd.Timedelta(minutes=15 * i)
        base = 1.2050 - (i * 0.0002)
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "mid_open": base,
                "mid_high": base + 0.0004,
                "mid_low": base - 0.0003,
                "mid_close": base - 0.0001,
            }
        )

    # Bearish day calculations.
    rows.extend(
        [
            {
                "timestamp": "2024-01-03T07:00:00Z",
                "mid_open": 1.2000,
                "mid_high": 1.2005,
                "mid_low": 1.1990,
                "mid_close": 1.1990,
            },
            {
                "timestamp": "2024-01-03T07:15:00Z",
                "mid_open": 1.1990,
                "mid_high": 1.1992,
                "mid_low": 1.1980,
                "mid_close": 1.1980,
            },
            {
                "timestamp": "2024-01-03T07:30:00Z",
                "mid_open": 1.1980,
                "mid_high": 1.1982,
                "mid_low": 1.1968,
                "mid_close": 1.1970,
            },
            {
                "timestamp": "2024-01-03T07:45:00Z",
                "mid_open": 1.1970,
                "mid_high": 1.1982,
                "mid_low": 1.1971,
                "mid_close": 1.1978,
            },
            {
                "timestamp": "2024-01-03T08:00:00Z",
                "mid_open": 1.1978,
                "mid_high": 1.1980,
                "mid_low": 1.1972,
                "mid_close": 1.1976,
            },
            {
                "timestamp": "2024-01-03T09:00:00Z",
                "mid_open": 1.1976,
                "mid_high": 1.1978,
                "mid_low": 1.1960,
                "mid_close": 1.1965,
            },
            {
                "timestamp": "2024-01-03T09:15:00Z",
                "mid_open": 1.1965,
                "mid_high": 1.1969,
                "mid_low": 1.1962,
                "mid_close": 1.1964,
            },
        ]
    )

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def test_impulse_calculation() -> None:
    module = load_script_module()
    daily = module.compute_daily_metrics(build_test_bars())
    first = daily[daily["date"] == "2024-01-02"].iloc[0]
    assert first["impulse_direction"] == "bullish"
    assert first["impulse_size"] == pytest.approx(0.0030)


def test_bullish_and_bearish_pullback_calculation() -> None:
    module = load_script_module()
    daily = module.compute_daily_metrics(build_test_bars())

    bull = daily[daily["date"] == "2024-01-02"].iloc[0]
    bear = daily[daily["date"] == "2024-01-03"].iloc[0]

    assert bull["pullback_ratio"] == pytest.approx(0.4666666667)
    assert bear["pullback_ratio"] == pytest.approx(0.4666666667)


def test_continuation_calculation() -> None:
    module = load_script_module()
    daily = module.compute_daily_metrics(build_test_bars())

    bull = daily[daily["date"] == "2024-01-02"].iloc[0]
    bear = daily[daily["date"] == "2024-01-03"].iloc[0]

    assert bull["continuation_ratio"] == pytest.approx(0.4)
    assert bear["continuation_ratio"] == pytest.approx(0.3333333333)


def test_output_file_creation(tmp_path: Path) -> None:
    module = load_script_module()
    daily = module.compute_daily_metrics(build_test_bars())
    dist = module.distribution_table(daily)
    summary = module.build_summary(daily, dataset_path="fake.parquet")

    module.write_outputs(tmp_path, daily, dist, summary)

    assert (tmp_path / "daily_metrics.csv").exists()
    assert (tmp_path / "distribution.csv").exists()
    assert (tmp_path / "summary.json").exists()
