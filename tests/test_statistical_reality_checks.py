from __future__ import annotations

import numpy as np
import pandas as pd

from eurusd_quant.research.statistical_reality_checks import (
    CandidatePattern,
    SensitivityVariant,
    assign_credibility_label,
    build_transition_observations,
    evaluate_pattern_observations,
    sample_filter_summary,
    summarize_pair_stability,
    summarize_sensitivity,
    summarize_yearly_stability,
)


def _session_state_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "pair": "EURUSD",
                "session": "asia",
                "session_start": pd.Timestamp("2024-01-02 00:00:00+00:00"),
                "session_end": pd.Timestamp("2024-01-02 06:45:00+00:00"),
                "session_date": pd.Timestamp("2024-01-02"),
                "session_return": 0.0004,
                "session_abs_return": 0.0004,
                "session_direction": "up",
                "session_direction_sign": 1.0,
                "volatility_regime": "low_vol",
                "range_regime": "normal",
                "directional_efficiency_ratio": 0.20,
                "close_location_value": 0.60,
                "structural_breach_presence": "breakout",
                "breach_direction": "upside",
                "breach_magnitude_bucket": "medium",
                "breakout_event_count": 2,
                "sweep_event_count": 0,
            },
            {
                "pair": "EURUSD",
                "session": "london",
                "session_start": pd.Timestamp("2024-01-02 07:00:00+00:00"),
                "session_end": pd.Timestamp("2024-01-02 12:45:00+00:00"),
                "session_date": pd.Timestamp("2024-01-02"),
                "session_return": 0.0007,
                "session_abs_return": 0.0007,
                "session_direction": "up",
                "session_direction_sign": 1.0,
                "volatility_regime": "medium_vol",
                "range_regime": "expanded",
                "directional_efficiency_ratio": 0.30,
                "close_location_value": 0.70,
                "structural_breach_presence": "sweep",
                "breach_direction": "upside",
                "breach_magnitude_bucket": "large",
                "breakout_event_count": 1,
                "sweep_event_count": 2,
            },
            {
                "pair": "EURUSD",
                "session": "new_york",
                "session_start": pd.Timestamp("2024-01-02 22:00:00+00:00"),
                "session_end": pd.Timestamp("2024-01-03 21:45:00+00:00"),
                "session_date": pd.Timestamp("2024-01-03"),
                "session_return": 0.0005,
                "session_abs_return": 0.0005,
                "session_direction": "up",
                "session_direction_sign": 1.0,
                "volatility_regime": "low_vol",
                "range_regime": "normal",
                "directional_efficiency_ratio": 0.22,
                "close_location_value": 0.58,
                "structural_breach_presence": "breakout",
                "breach_direction": "upside",
                "breach_magnitude_bucket": "medium",
                "breakout_event_count": 3,
                "sweep_event_count": 0,
            },
        ]
    )


def test_build_transition_observations_keeps_previous_session_context() -> None:
    transitions = build_transition_observations(_session_state_rows())

    assert list(transitions["transition_type"]) == ["asia_to_london", "london_to_new_york"]
    london_to_ny = transitions.iloc[1]
    assert london_to_ny["previous_session_name"] == "asia"
    assert london_to_ny["current_range_regime"] == "expanded"
    assert london_to_ny["next_continuation_flag"] == 1.0


def test_evaluate_pattern_observations_reports_pips_and_ci() -> None:
    frame = pd.DataFrame(
        {
            "pair": ["EURUSD", "EURUSD", "EURUSD"],
            "outcome": [0.0002, 0.0001, -0.0001],
            "continuation": [1.0, 1.0, 0.0],
            "reversal": [0.0, 0.0, 1.0],
            "outcome_pip_multiplier": [10000.0, 10000.0, 10000.0],
        }
    )

    metrics = evaluate_pattern_observations(
        frame,
        outcome_col="outcome",
        continuation_col="continuation",
        reversal_col="reversal",
    )

    assert metrics["sample_count"] == 3
    assert np.isclose(metrics["mean_outcome"], 0.0000666667)
    assert np.isclose(metrics["mean_outcome_pips"], 0.6666667)
    assert metrics["friction_survives_1pip"] is False
    assert metrics["ci_upper"] > metrics["ci_lower"]


def test_yearly_and_pair_stability_summaries_respect_thresholds() -> None:
    frame = pd.DataFrame(
        {
            "pair": ["EURUSD", "EURUSD", "USDJPY", "USDJPY"],
            "year": [2023, 2024, 2023, 2024],
            "outcome": [0.0003, -0.0001, 0.0002, 0.0004],
            "continuation": [1.0, 0.0, 1.0, 1.0],
            "reversal": [0.0, 1.0, 0.0, 0.0],
            "outcome_pip_multiplier": [10000.0, 10000.0, 100.0, 100.0],
        }
    )
    pattern = CandidatePattern(
        pattern_id="toy",
        pattern_family="session_transition",
        pair_scope="pooled",
        source_phase="R6",
        brief_description="toy",
        dataset_name="transition_observations",
        outcome_col="outcome",
        continuation_col="continuation",
        reversal_col="reversal",
        horizon_label="next_session",
        selector=lambda source: source["outcome"].notna(),
    )

    yearly_df, yearly_diag = summarize_yearly_stability(pattern, frame)
    pair_df, pair_diag = summarize_pair_stability(pattern, frame)

    assert set(yearly_df["year"]) == {2023, 2024}
    assert yearly_diag["positive_years"] == 2
    assert set(pair_df["pair"]) == {"EURUSD", "USDJPY"}
    assert pair_diag["pairs_positive"] == 2


def test_sensitivity_summary_tracks_sign_and_sample_changes() -> None:
    frame = pd.DataFrame(
        {
            "pair": ["EURUSD"] * 5,
            "year": [2024] * 5,
            "outcome": [0.0003, 0.0002, 0.0001, -0.0002, -0.0003],
            "continuation": [1.0, 1.0, 1.0, 0.0, 0.0],
            "reversal": [0.0, 0.0, 0.0, 1.0, 1.0],
            "outcome_pip_multiplier": [10000.0] * 5,
            "keep_all": [True] * 5,
            "positive_only": [True, True, True, False, False],
            "tail_only": [False, False, False, True, True],
        }
    )
    pattern = CandidatePattern(
        pattern_id="toy",
        pattern_family="session_transition",
        pair_scope="pooled",
        source_phase="R6",
        brief_description="toy",
        dataset_name="transition_observations",
        outcome_col="outcome",
        continuation_col="continuation",
        reversal_col="reversal",
        horizon_label="next_session",
        selector=lambda source: source["keep_all"],
        sensitivity_variants=(
            SensitivityVariant("positive_only", "positive cluster", lambda source: source["positive_only"]),
            SensitivityVariant("tail_only", "negative cluster", lambda source: source["tail_only"]),
        ),
    )

    summary, diagnostics = summarize_sensitivity(pattern, frame, base_sample_count=5, base_mean_outcome=0.00002)

    assert list(summary["variant_id"]) == ["positive_only", "tail_only"]
    assert diagnostics["sensitivity_sign_consistent"] is False
    assert diagnostics["sensitivity_sample_consistent"] is True


def test_assign_credibility_label_prefers_conservative_outcomes() -> None:
    pattern = CandidatePattern(
        pattern_id="toy",
        pattern_family="session_transition",
        pair_scope="USDJPY",
        source_phase="R6",
        brief_description="toy",
        dataset_name="transition_observations",
        outcome_col="outcome",
        horizon_label="next_session",
        selector=lambda source: source["pair"] == "USDJPY",
    )
    base_metrics = {
        "mean_outcome": 0.00025,
        "friction_survives_1pip": True,
    }
    sample_filters = sample_filter_summary(
        pattern,
        base_sample_count=220,
        years_with_min_sample=5,
        pairs_with_min_sample=1,
    )
    yearly_diag = {
        "years_with_min_sample": 5,
        "positive_years": 5,
        "negative_years": 1,
        "largest_year_share": 0.30,
    }
    pair_diag = {
        "pairs_with_min_sample": 1,
        "pairs_positive": 1,
        "mean_outcome_variance": 0.0,
    }
    sensitivity_diag = {
        "sensitivity_sign_consistent": True,
        "sensitivity_sample_consistent": True,
    }

    label, reason = assign_credibility_label(
        pattern,
        base_metrics,
        sample_filters,
        yearly_diag,
        pair_diag,
        sensitivity_diag,
    )

    assert label == "pair_specific_candidate"
    assert "pair-specific" in reason
