from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_ny_impulse_volatility_regime.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("ny_vol_regime", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load analysis script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_assign_volatility_regimes_splits_three_buckets() -> None:
    module = load_script_module()
    atr = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    regimes, thresholds = module.assign_volatility_regimes(atr)

    assert thresholds["p30"] == pytest.approx(2.2)
    assert thresholds["p70"] == pytest.approx(3.8)
    assert set(regimes.unique()) == {"low_vol", "mid_vol", "high_vol"}


def test_compute_regime_metrics_returns_expected_counts() -> None:
    module = load_script_module()
    df = pd.DataFrame(
        {
            "volatility_regime": ["low_vol", "low_vol", "mid_vol", "high_vol"],
            "entry_time": pd.to_datetime(
                [
                    "2024-01-01 13:30:00+00:00",
                    "2024-01-02 13:30:00+00:00",
                    "2024-01-03 13:30:00+00:00",
                    "2024-01-04 13:30:00+00:00",
                ],
                utc=True,
            ),
            "exit_time": pd.to_datetime(
                [
                    "2024-01-01 14:00:00+00:00",
                    "2024-01-02 14:00:00+00:00",
                    "2024-01-03 14:00:00+00:00",
                    "2024-01-04 14:00:00+00:00",
                ],
                utc=True,
            ),
            "net_pnl": [1.0, -0.5, 0.25, 0.0],
            "gross_pnl": [1.0, -0.5, 0.25, 0.0],
        }
    )

    metrics = module.compute_regime_metrics(df)
    by_regime = {row["regime"]: row for row in metrics}

    assert by_regime["low_vol"]["trade_count"] == 2
    assert by_regime["low_vol"]["win_rate"] == pytest.approx(0.5)
    assert by_regime["mid_vol"]["trade_count"] == 1
    assert by_regime["mid_vol"]["net_pnl"] == pytest.approx(0.25)
    assert by_regime["high_vol"]["trade_count"] == 1
