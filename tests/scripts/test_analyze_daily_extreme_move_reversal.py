from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "analyze_daily_extreme_move_reversal.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("daily_extreme_move_reversal", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load daily extreme move reversal script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_intraday(day: str, base: float, close: float) -> list[dict]:
    return [
        {"timestamp": f"{day}T00:00:00Z", "mid_open": base, "mid_high": max(base, close) + 0.0005, "mid_low": min(base, close) - 0.0005, "mid_close": base + (close-base)/2},
        {"timestamp": f"{day}T23:45:00Z", "mid_open": base + (close-base)/2, "mid_high": max(base, close) + 0.0003, "mid_low": min(base, close) - 0.0003, "mid_close": close},
    ]


def make_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["symbol"] = "EURUSD"
    return df.sort_values("timestamp").reset_index(drop=True)


def test_daily_aggregation_and_strong_flag() -> None:
    module = load_script_module()
    rows = []
    rows += make_intraday("2024-01-01", 1.1000, 1.1030)
    rows += make_intraday("2024-01-02", 1.1030, 1.1010)
    bars = make_bars(rows)

    daily = module.compute_daily_metrics(bars, threshold_atr=0.5)
    assert len(daily) == 2
    assert bool(daily.iloc[0]["strong_momentum_flag"]) is True


def test_reversal_vs_continuation_sign() -> None:
    module = load_script_module()
    rows = []
    rows += make_intraday("2024-01-01", 1.1000, 1.1030)  # up momentum
    rows += make_intraday("2024-01-02", 1.1030, 1.1010)  # next day down -> reversal
    bars = make_bars(rows)

    daily = module.compute_daily_metrics(bars, threshold_atr=0.1)
    first = daily.iloc[0]
    assert first["continuation_1d"] < 0
    assert first["reversal_1d"] > 0
    assert first["reversal_1d_atr"] > 0


def test_summary_fields_present() -> None:
    module = load_script_module()
    rows = []
    rows += make_intraday("2024-01-01", 1.1000, 1.1030)
    rows += make_intraday("2024-01-02", 1.1030, 1.1010)
    rows += make_intraday("2024-01-03", 1.1010, 1.1020)
    bars = make_bars(rows)

    daily = module.compute_daily_metrics(bars, threshold_atr=0.1)
    summary = module.build_summary(daily, dataset_path="test.parquet", threshold_atr=0.1)
    assert "reversal_probability_1d" in summary
    assert "continuation_probability_1d" in summary
    assert summary["days_analyzed"] == 3
