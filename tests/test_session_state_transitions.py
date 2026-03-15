from __future__ import annotations

import pandas as pd

from eurusd_quant.research.session_state_transitions import (
    build_three_session_patterns,
    build_two_session_transitions,
    classify_session_direction,
    expected_next_session,
)


def _sample_session_states() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pair": ["EURUSD"] * 4,
            "session_date": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-01", "2024-01-02"]),
            "fx_session_date": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-01", "2024-01-02"]),
            "session": ["asia", "london", "new_york", "asia"],
            "session_start": pd.to_datetime(
                [
                    "2024-01-01 00:00:00+00:00",
                    "2024-01-01 07:00:00+00:00",
                    "2024-01-01 13:00:00+00:00",
                    "2024-01-02 00:00:00+00:00",
                ]
            ),
            "session_end": pd.to_datetime(
                [
                    "2024-01-01 06:45:00+00:00",
                    "2024-01-01 12:45:00+00:00",
                    "2024-01-01 23:45:00+00:00",
                    "2024-01-02 06:45:00+00:00",
                ]
            ),
            "session_return": [0.0010, 0.0020, -0.0010, -0.0005],
            "session_abs_return": [0.0010, 0.0020, 0.0010, 0.0005],
            "session_range": [0.0020, 0.0030, 0.0025, 0.0015],
            "session_direction": ["up", "up", "down", "down"],
            "session_direction_sign": [1.0, 1.0, -1.0, -1.0],
            "volatility_regime": ["low_vol", "medium_vol", "high_vol", "medium_vol"],
            "range_regime": ["compressed", "expanded", "expanded", "normal"],
            "directional_efficiency_ratio": [0.2, 0.4, 0.35, 0.25],
            "close_location_value": [0.6, 0.7, 0.3, 0.4],
            "structural_breach_presence": ["none", "breakout", "sweep", "none"],
            "breach_direction": ["none", "upside", "downside", "none"],
            "breach_magnitude_bucket": ["none", "large", "medium", "none"],
            "breakout_event_count": [0, 3, 0, 0],
            "sweep_event_count": [0, 0, 2, 0],
            "breach_event_count": [0, 3, 2, 0],
        }
    )


def test_classify_session_direction_marks_flat_conservatively() -> None:
    labels, signs = classify_session_direction(pd.Series([0.001, -0.002, 0.0, 1e-7]))

    assert labels.tolist() == ["up", "down", "flat", "flat"]
    assert signs.tolist() == [1.0, -1.0, 0.0, 0.0]


def test_expected_next_session_cycles_in_fx_order() -> None:
    assert expected_next_session("asia") == "london"
    assert expected_next_session("london") == "new_york"
    assert expected_next_session("new_york") == "asia"


def test_build_two_session_transitions_aligns_current_vs_previous_direction() -> None:
    transitions = build_two_session_transitions(_sample_session_states())

    assert len(transitions) == 3
    asia_london = transitions.loc[transitions["transition_type"] == "asia_to_london"].iloc[0]
    london_ny = transitions.loc[transitions["transition_type"] == "london_to_new_york"].iloc[0]

    assert asia_london["continuation_flag"] == 1.0
    assert asia_london["reversal_flag"] == 0.0
    assert london_ny["continuation_flag"] == 0.0
    assert london_ny["reversal_flag"] == 1.0


def test_build_three_session_patterns_aligns_next_vs_current_direction() -> None:
    patterns = build_three_session_patterns(_sample_session_states())

    assert len(patterns) == 2
    first = patterns.iloc[0]
    second = patterns.iloc[1]

    assert first["transition_type"] == "asia_to_london"
    assert first["next_session_name"] == "new_york"
    assert first["next_continuation_flag"] == 0.0
    assert first["next_reversal_flag"] == 1.0

    assert second["transition_type"] == "london_to_new_york"
    assert second["next_session_name"] == "asia"
    assert second["next_continuation_flag"] == 1.0
    assert second["next_reversal_flag"] == 0.0
