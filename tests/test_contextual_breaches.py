from __future__ import annotations

import pandas as pd

from eurusd_quant.research.contextual_breaches import (
    assign_session_subcontext,
    assign_transition_context,
    bucket_magnitude,
    build_contextual_breach_inventory,
)


def test_assign_session_subcontext_splits_session_into_thirds() -> None:
    bar_index = pd.Series([0, 2, 3, 5, 6, 8])
    session_count = pd.Series([9] * 6)

    result = assign_session_subcontext(bar_index, session_count)

    assert result.tolist() == [
        "early_session",
        "early_session",
        "mid_session",
        "mid_session",
        "late_session",
        "late_session",
    ]


def test_assign_transition_context_marks_boundary_windows() -> None:
    session = pd.Series(["asia", "london", "london", "new_york", "new_york"])
    bar_index = pd.Series([2, 0, 5, 1, 7])

    result = assign_transition_context(session, bar_index, boundary_bars=4)

    assert result.tolist() == [
        "inside_asia",
        "asia_to_london_boundary",
        "inside_london",
        "london_to_new_york_boundary",
        "inside_new_york",
    ]


def test_bucket_magnitude_creates_small_medium_large_groups() -> None:
    values = pd.Series([0.1, 0.2, 0.3, 1.0, 1.2, 1.5, 2.0, 2.1, 3.0])

    result = bucket_magnitude(values)

    assert set(result.unique()) == {"small", "medium", "large"}
    assert result.iloc[0] == "small"
    assert result.iloc[-1] == "large"


def test_build_contextual_breach_inventory_aligns_directional_outcomes() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01 00:00:00", periods=6, freq="15min", tz="UTC"),
            "fx_session_date": [pd.Timestamp("2024-01-01")] * 6,
            "session": ["london"] * 6,
            "bar_index_within_session": [0, 1, 2, 3, 4, 5],
            "session_subcontext": ["early_session"] * 6,
            "transition_context": ["asia_to_london_boundary"] * 6,
            "volatility_regime": ["medium_vol"] * 6,
            "range_regime": ["compressed"] * 6,
            "atr": [0.01] * 6,
            "mid_open": [1.00, 1.01, 1.02, 1.03, 1.04, 1.05],
            "mid_high": [1.05, 1.06, 1.07, 1.11, 1.12, 1.08],
            "mid_low": [0.95, 0.96, 0.97, 1.00, 0.94, 1.00],
            "mid_close": [1.02, 1.03, 1.04, 1.08, 0.98, 1.07],
        }
    )

    inventory, outcomes = build_contextual_breach_inventory(frame, pair="EURUSD", lookback_windows=(3,), horizons=(1,))
    merged = inventory.merge(outcomes, on="event_id", how="inner")

    breakout_high = merged.loc[merged["event_type"] == "breakout_high"].iloc[0]
    sweep_low = merged.loc[merged["event_type"] == "sweep_low"].iloc[0]

    assert breakout_high["direction"] == "upside"
    assert breakout_high["continuation_flag_1"] == 0.0
    assert breakout_high["reversal_flag_1"] == 1.0
    assert breakout_high["magnitude_bucket"] in {"small", "medium", "large"}

    assert sweep_low["direction"] == "downside"
    assert sweep_low["aligned_forward_return_1"] < 0
    assert sweep_low["reversal_flag_1"] == 1.0
