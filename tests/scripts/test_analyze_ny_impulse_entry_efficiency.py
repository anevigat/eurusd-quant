from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_ny_impulse_entry_efficiency.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("ny_entry_eff", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load analysis script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compute_trade_entry_efficiency_long_and_short() -> None:
    module = load_script_module()

    bars = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-01-01 14:00:00+00:00",
                    "2024-01-01 14:15:00+00:00",
                    "2024-01-01 14:30:00+00:00",
                ],
                utc=True,
            ),
            "ask_low": [1.09, 1.08, 1.11],
            "bid_high": [1.21, 1.24, 1.20],
        }
    )

    long_trade = pd.Series({"side": "long", "entry_price": 1.10, "exit_price": 1.12})
    short_trade = pd.Series({"side": "short", "entry_price": 1.20, "exit_price": 1.15})

    long_eff = module.compute_trade_entry_efficiency(long_trade, bars)
    short_eff = module.compute_trade_entry_efficiency(short_trade, bars)

    assert long_eff == pytest.approx(0.5)
    assert short_eff == pytest.approx((1.24 - 1.20) / abs(1.24 - 1.15))


def test_efficiency_is_clipped_to_unit_interval() -> None:
    module = load_script_module()
    bars = pd.DataFrame({"ask_low": [1.12], "bid_high": [1.20]})

    # Negative raw ratio -> clipped to 0.
    trade = pd.Series({"side": "long", "entry_price": 1.10, "exit_price": 1.30})
    eff = module.compute_trade_entry_efficiency(trade, bars)
    assert eff == pytest.approx(0.0)


def test_summarize_efficiency_quantiles() -> None:
    module = load_script_module()
    series = pd.Series([0.2, 0.4, 0.6, 0.8, 1.0])
    summary = module.summarize_efficiency(series)

    assert summary["mean"] == pytest.approx(0.6)
    assert summary["median"] == pytest.approx(0.6)
    assert summary["p25"] == pytest.approx(0.4)
    assert summary["p75"] == pytest.approx(0.8)
    assert summary["p90"] == pytest.approx(0.92)
