from __future__ import annotations

import pandas as pd

from eurusd_quant.research.structural_extremes import (
    add_forward_returns,
    build_extreme_event_inventory,
    compute_structural_levels,
)


def test_compute_structural_levels_uses_only_prior_bars() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01 00:00:00", periods=5, freq="15min", tz="UTC"),
            "mid_high": [1.10, 1.11, 1.12, 1.20, 1.18],
            "mid_low": [1.00, 1.01, 1.02, 1.03, 1.04],
            "mid_close": [1.05, 1.06, 1.07, 1.19, 1.17],
        }
    )

    result = compute_structural_levels(frame, lookback_windows=(3,))

    assert pd.isna(result.loc[2, "rolling_high_3"])
    assert result.loc[3, "rolling_high_3"] == 1.12
    assert result.loc[3, "rolling_low_3"] == 1.00
    assert bool(result.loc[3, "break_above_high_3"]) is True


def test_build_extreme_event_inventory_classifies_sweeps_and_breakouts() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01 00:00:00", periods=6, freq="15min", tz="UTC"),
            "fx_session_date": [pd.Timestamp("2024-01-01")] * 6,
            "session": ["london"] * 6,
            "volatility_regime": ["medium_vol"] * 6,
            "mid_open": [1.00, 1.01, 1.02, 1.03, 1.04, 1.05],
            "mid_high": [1.05, 1.06, 1.07, 1.11, 1.12, 1.08],
            "mid_low": [0.95, 0.96, 0.97, 1.00, 0.94, 1.00],
            "mid_close": [1.02, 1.03, 1.04, 1.08, 0.98, 1.07],
        }
    )

    events = build_extreme_event_inventory(frame, pair="EURUSD", lookback_windows=(3,), horizons=(1,))

    assert set(events["event_type"]) == {"breakout_high", "sweep_low", "sweep_high"}
    breakout_row = events.loc[events["event_type"] == "breakout_high"].iloc[0]
    sweep_high_row = events.loc[events["event_type"] == "sweep_high"].iloc[0]
    sweep_low_row = events.loc[events["event_type"] == "sweep_low"].iloc[0]

    assert breakout_row["timestamp"] == pd.Timestamp("2024-01-01 00:45:00+00:00")
    assert sweep_low_row["timestamp"] == pd.Timestamp("2024-01-01 01:00:00+00:00")
    assert sweep_high_row["timestamp"] == pd.Timestamp("2024-01-01 01:00:00+00:00")
    assert breakout_row["continuation_flag_1"] == 0.0
    assert breakout_row["reversal_flag_1"] == 1.0
    assert sweep_low_row["continuation_flag_1"] == 0.0
    assert sweep_low_row["reversal_flag_1"] == 1.0


def test_add_forward_returns_uses_future_close() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01 00:00:00", periods=4, freq="15min", tz="UTC"),
            "mid_close": [1.00, 1.02, 1.01, 1.03],
        }
    )

    result = add_forward_returns(frame, horizons=(1, 2))

    assert round(result.loc[0, "forward_return_1"], 6) == 0.02
    assert round(result.loc[0, "forward_return_2"], 6) == 0.01
    assert pd.isna(result.loc[3, "forward_return_1"])
