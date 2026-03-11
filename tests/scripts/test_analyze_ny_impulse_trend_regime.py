from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_ny_impulse_trend_regime.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("ny_trend_regime", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load analysis script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_assign_trend_regimes_thresholds() -> None:
    module = load_script_module()
    trend = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5])
    regimes, thresholds = module.assign_trend_regimes(trend)

    assert thresholds["p30"] == pytest.approx(0.22)
    assert thresholds["p70"] == pytest.approx(0.38)
    assert set(regimes.unique()) == {"range_day", "normal_day", "trend_day"}


def test_compute_regime_metrics_counts() -> None:
    module = load_script_module()
    df = pd.DataFrame(
        {
            "trend_regime": ["range_day", "normal_day", "normal_day", "trend_day"],
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

    assert by_regime["range_day"]["trade_count"] == 1
    assert by_regime["normal_day"]["trade_count"] == 2
    assert by_regime["normal_day"]["win_rate"] == pytest.approx(0.5)
    assert by_regime["trend_day"]["net_pnl"] == pytest.approx(0.0)
