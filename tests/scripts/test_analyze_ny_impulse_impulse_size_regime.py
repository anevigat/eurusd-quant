from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_ny_impulse_impulse_size_regime.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("ny_impulse_regime", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load analysis script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_assign_impulse_regimes_thresholds() -> None:
    module = load_script_module()
    impulse = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    regimes, thresholds = module.assign_impulse_regimes(impulse)

    assert thresholds["p50"] == pytest.approx(3.0)
    assert thresholds["p75"] == pytest.approx(4.0)
    assert thresholds["p90"] == pytest.approx(4.6)
    assert regimes.iloc[0] == "small_impulse"
    assert regimes.iloc[3] == "medium_impulse"
    assert regimes.iloc[4] == "extreme_impulse"


def test_compute_regime_metrics_counts() -> None:
    module = load_script_module()
    df = pd.DataFrame(
        {
            "impulse_regime": [
                "small_impulse",
                "medium_impulse",
                "large_impulse",
                "extreme_impulse",
            ],
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
        }
    )

    metrics = module.compute_regime_metrics(df)
    by_regime = {row["regime"]: row for row in metrics}

    assert by_regime["small_impulse"]["trade_count"] == 1
    assert by_regime["small_impulse"]["win_rate"] == pytest.approx(1.0)
    assert by_regime["medium_impulse"]["trade_count"] == 1
    assert by_regime["medium_impulse"]["net_pnl"] == pytest.approx(-0.5)
    assert by_regime["extreme_impulse"]["trade_count"] == 1
