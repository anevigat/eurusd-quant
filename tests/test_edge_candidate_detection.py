from __future__ import annotations

import numpy as np
import pandas as pd

from eurusd_quant.research.edge_candidate_detection import (
    build_candidate_outcome_profiles,
    build_candidate_region_subregions,
    generate_edge_candidate_definitions,
    load_base_candidate_region,
    summarize_candidate_region,
)


def test_load_base_candidate_region_filters_expanded_and_adds_context(tmp_path) -> None:
    diagnostics = tmp_path / "outputs" / "diagnostics"
    (diagnostics / "contextual_breaches").mkdir(parents=True)
    (diagnostics / "session_state_transitions").mkdir(parents=True)

    inventory = pd.DataFrame(
        [
            {
                "event_id": 1,
                "pair": "EURUSD",
                "timestamp": "2024-01-02T07:00:00Z",
                "fx_session_date": "2024-01-02",
                "session": "london",
                "session_subcontext": "early_session",
                "transition_context": "inside_london",
                "volatility_regime": "medium_vol",
                "range_regime": "expanded",
                "lookback_window": 24,
                "event_type": "breakout_low",
                "event_class": "breakout",
                "direction": "downside",
                "magnitude_bucket": "small",
                "breach_magnitude_pips": 2.0,
                "breach_magnitude_atr": 0.5,
            },
            {
                "event_id": 2,
                "pair": "EURUSD",
                "timestamp": "2024-01-02T14:00:00Z",
                "fx_session_date": "2024-01-02",
                "session": "new_york",
                "session_subcontext": "early_session",
                "transition_context": "london_to_new_york_boundary",
                "volatility_regime": "high_vol",
                "range_regime": "normal",
                "lookback_window": 24,
                "event_type": "sweep_high",
                "event_class": "sweep",
                "direction": "upside",
                "magnitude_bucket": "medium",
                "breach_magnitude_pips": 3.0,
                "breach_magnitude_atr": 0.8,
            },
        ]
    )
    inventory.to_csv(diagnostics / "contextual_breaches" / "contextual_breach_inventory.csv", index=False)

    outcomes = pd.DataFrame(
        [
            {
                "event_id": 1,
                "forward_return_1": -0.0001,
                "aligned_forward_return_1": 0.0001,
                "continuation_flag_1": 1,
                "reversal_flag_1": 0,
                "mfe_1": 0.0002,
                "mae_1": 0.0001,
                "forward_return_2": -0.0002,
                "aligned_forward_return_2": 0.0002,
                "continuation_flag_2": 1,
                "reversal_flag_2": 0,
                "mfe_2": 0.0003,
                "mae_2": 0.0002,
                "forward_return_4": -0.0003,
                "aligned_forward_return_4": 0.0003,
                "continuation_flag_4": 1,
                "reversal_flag_4": 0,
                "mfe_4": 0.0004,
                "mae_4": 0.0002,
                "forward_return_8": -0.0005,
                "aligned_forward_return_8": 0.0005,
                "continuation_flag_8": 1,
                "reversal_flag_8": 0,
                "mfe_8": 0.0006,
                "mae_8": 0.0003,
            },
            {
                "event_id": 2,
                "forward_return_1": 0.0001,
                "aligned_forward_return_1": 0.0001,
                "continuation_flag_1": 1,
                "reversal_flag_1": 0,
                "mfe_1": 0.0002,
                "mae_1": 0.0001,
                "forward_return_2": 0.0002,
                "aligned_forward_return_2": 0.0002,
                "continuation_flag_2": 1,
                "reversal_flag_2": 0,
                "mfe_2": 0.0003,
                "mae_2": 0.0001,
                "forward_return_4": 0.0002,
                "aligned_forward_return_4": 0.0002,
                "continuation_flag_4": 1,
                "reversal_flag_4": 0,
                "mfe_4": 0.0004,
                "mae_4": 0.0001,
                "forward_return_8": 0.0003,
                "aligned_forward_return_8": 0.0003,
                "continuation_flag_8": 1,
                "reversal_flag_8": 0,
                "mfe_8": 0.0005,
                "mae_8": 0.0001,
            },
        ]
    )
    outcomes.to_csv(diagnostics / "contextual_breaches" / "contextual_breach_outcomes.csv", index=False)

    session_states = pd.DataFrame(
        [
            {
                "pair": "EURUSD",
                "fx_session_date": "2024-01-02",
                "session": "london",
                "session_range": 0.0040,
            },
            {
                "pair": "EURUSD",
                "fx_session_date": "2024-01-02",
                "session": "new_york",
                "session_range": 0.0050,
            },
        ]
    )
    session_states.to_csv(diagnostics / "session_state_transitions" / "session_state_inventory.csv", index=False)

    region = load_base_candidate_region(diagnostics)

    assert len(region) == 1
    assert region.iloc[0]["time_context"] == "London"
    assert region.iloc[0]["expanded_intensity"] in {"strongly_expanded", "moderately_expanded"}


def test_summarize_candidate_region_computes_expected_metrics() -> None:
    frame = pd.DataFrame(
        {
            "aligned_forward_return_4": [0.0004, 0.0002, 0.0001],
            "forward_return_4": [-0.0004, -0.0002, -0.0001],
            "continuation_flag_4": [1, 1, 1],
            "reversal_flag_4": [0, 0, 0],
            "mfe_4": [0.0005, 0.0003, 0.0002],
            "mae_4": [0.0001, 0.0001, 0.0001],
            "pip_multiplier": [10000.0, 10000.0, 10000.0],
        }
    )

    summary = summarize_candidate_region(frame, horizon=4)

    assert summary["sample_count"] == 3
    assert np.isclose(summary["mean_return"], 0.0002333333)
    assert np.isclose(summary["continuation_fraction"], 1.0)
    assert np.isclose(summary["mean_return_pips"], 2.3333333)


def _synthetic_region() -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    def append_rows(
        *,
        pair: str,
        time_context: str,
        expanded_intensity: str,
        event_type: str,
        magnitude_bucket: str,
        direction: str,
        n: int,
        h1: float,
        h2: float,
        h4: float,
        h8: float,
        continuation: float = 1.0,
    ) -> None:
        raw_sign = -1.0 if direction == "downside" else 1.0
        for _ in range(n):
            rows.append(
                {
                    "pair": pair,
                    "time_context": time_context,
                    "expanded_intensity": expanded_intensity,
                    "event_type": event_type,
                    "magnitude_bucket": magnitude_bucket,
                    "direction": direction,
                    "volatility_regime": "all",
                    "range_regime": "expanded",
                    "lookback_window": 24,
                    "aligned_forward_return_1": h1,
                    "aligned_forward_return_2": h2,
                    "aligned_forward_return_4": h4,
                    "aligned_forward_return_8": h8,
                    "forward_return_1": raw_sign * h1,
                    "forward_return_2": raw_sign * h2,
                    "forward_return_4": raw_sign * h4,
                    "forward_return_8": raw_sign * h8,
                    "continuation_flag_1": continuation,
                    "continuation_flag_2": continuation,
                    "continuation_flag_4": continuation,
                    "continuation_flag_8": continuation,
                    "reversal_flag_1": 1.0 - continuation,
                    "reversal_flag_2": 1.0 - continuation,
                    "reversal_flag_4": 1.0 - continuation,
                    "reversal_flag_8": 1.0 - continuation,
                    "mfe_1": h1 * 1.5,
                    "mfe_2": h2 * 1.5,
                    "mfe_4": h4 * 1.5,
                    "mfe_8": h8 * 1.5,
                    "mae_1": h1 * 0.25,
                    "mae_2": h2 * 0.25,
                    "mae_4": h4 * 0.25,
                    "mae_8": h8 * 0.25,
                    "pip_multiplier": 100.0 if pair == "USDJPY" else 10000.0,
                }
            )

    append_rows(
        pair="EURUSD",
        time_context="London",
        expanded_intensity="strongly_expanded",
        event_type="breakout_low",
        magnitude_bucket="small",
        direction="downside",
        n=450,
        h1=0.0002,
        h2=0.0004,
        h4=0.0008,
        h8=0.0012,
    )
    append_rows(
        pair="GBPUSD",
        time_context="early New York",
        expanded_intensity="strongly_expanded",
        event_type="sweep_low",
        magnitude_bucket="medium",
        direction="downside",
        n=430,
        h1=0.00025,
        h2=0.00035,
        h4=0.00065,
        h8=0.0009,
    )
    append_rows(
        pair="USDJPY",
        time_context="New York",
        expanded_intensity="strongly_expanded",
        event_type="breakout_high",
        magnitude_bucket="small",
        direction="upside",
        n=240,
        h1=0.00012,
        h2=0.0002,
        h4=0.00032,
        h8=0.0005,
    )
    append_rows(
        pair="EURUSD",
        time_context="London",
        expanded_intensity="moderately_expanded",
        event_type="sweep_high",
        magnitude_bucket="small",
        direction="upside",
        n=500,
        h1=0.00001,
        h2=0.00001,
        h4=0.00001,
        h8=0.00001,
        continuation=0.45,
    )
    return pd.DataFrame(rows)


def test_build_candidate_region_subregions_includes_requested_breakdowns() -> None:
    subregions = build_candidate_region_subregions(_synthetic_region())

    assert "pair__time_context__expanded_intensity__event_type" in set(subregions["breakdown_family"])
    london_rows = subregions[subregions["time_context"] == "London"]
    assert not london_rows.empty


def test_generate_edge_candidate_definitions_and_profiles() -> None:
    region = _synthetic_region()
    definitions = generate_edge_candidate_definitions(region)

    assert not definitions.empty
    assert definitions["range_regime"].eq("strongly_expanded").all()
    assert (definitions["sample_count"] >= 200).all()

    profiles = build_candidate_outcome_profiles(region, definitions.head(2))
    assert {"base_region", definitions.iloc[0]["candidate_id"], definitions.iloc[1]["candidate_id"]}.issubset(
        set(profiles["region_id"])
    )
