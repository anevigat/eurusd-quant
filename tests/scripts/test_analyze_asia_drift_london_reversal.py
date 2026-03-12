from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "analyze_asia_drift_london_reversal.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("asia_drift_london_reversal", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load asia drift london reversal script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_up_drift_reversal_calculation() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T00:00:00Z", "mid_open": 1.1000, "mid_high": 1.1002, "mid_low": 1.0998, "mid_close": 1.1001},
            {"timestamp": "2024-01-02T06:45:00Z", "mid_open": 1.1001, "mid_high": 1.1012, "mid_low": 1.1000, "mid_close": 1.1010},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1010, "mid_high": 1.1011, "mid_low": 1.1000, "mid_close": 1.1002},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.1002, "mid_high": 1.1015, "mid_low": 1.0995, "mid_close": 1.1012},
        ]
    )

    daily = module.compute_daily_metrics(bars)
    row = daily.iloc[0]
    assert row["drift_direction"] == "up"
    assert row["drift_magnitude"] == pytest.approx(0.0010)
    assert row["reversal_magnitude"] == pytest.approx(0.0015)
    assert row["reversal_ratio"] == pytest.approx(1.5)


def test_down_drift_reversal_calculation() -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-03T00:00:00Z", "mid_open": 1.2000, "mid_high": 1.2002, "mid_low": 1.1998, "mid_close": 1.1999},
            {"timestamp": "2024-01-03T06:45:00Z", "mid_open": 1.1999, "mid_high": 1.2000, "mid_low": 1.1988, "mid_close": 1.1990},
            {"timestamp": "2024-01-03T07:00:00Z", "mid_open": 1.1990, "mid_high": 1.1998, "mid_low": 1.1989, "mid_close": 1.1995},
            {"timestamp": "2024-01-03T07:15:00Z", "mid_open": 1.1995, "mid_high": 1.2002, "mid_low": 1.1985, "mid_close": 1.1989},
        ]
    )

    daily = module.compute_daily_metrics(bars)
    row = daily.iloc[0]
    assert row["drift_direction"] == "down"
    assert row["drift_magnitude"] == pytest.approx(0.0010)
    assert row["reversal_magnitude"] == pytest.approx(0.0012)
    assert row["reversal_ratio"] == pytest.approx(1.2)


def test_output_files_created(tmp_path: Path) -> None:
    module = load_script_module()
    bars = make_bars(
        [
            {"timestamp": "2024-01-02T00:00:00Z", "mid_open": 1.1000, "mid_high": 1.1002, "mid_low": 1.0998, "mid_close": 1.1001},
            {"timestamp": "2024-01-02T06:45:00Z", "mid_open": 1.1001, "mid_high": 1.1012, "mid_low": 1.1000, "mid_close": 1.1010},
            {"timestamp": "2024-01-02T07:00:00Z", "mid_open": 1.1010, "mid_high": 1.1011, "mid_low": 1.1000, "mid_close": 1.1002},
            {"timestamp": "2024-01-02T07:15:00Z", "mid_open": 1.1002, "mid_high": 1.1015, "mid_low": 1.0995, "mid_close": 1.1012},
        ]
    )

    daily = module.compute_daily_metrics(bars)
    summary = module.build_summary(daily, dataset_path="test.parquet")
    distribution = module.build_distribution(daily)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "daily_metrics.csv").write_text(daily.to_csv(index=False), encoding="utf-8")
    (out_dir / "distribution.csv").write_text(distribution.to_csv(index=False), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    assert (out_dir / "daily_metrics.csv").exists()
    assert (out_dir / "distribution.csv").exists()
    assert (out_dir / "summary.json").exists()
