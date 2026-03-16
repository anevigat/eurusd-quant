from __future__ import annotations

import pandas as pd

from eurusd_quant.research.strategy_experiment_catalog import (
    build_experiment_catalog,
    build_validation_ladder,
)


def _hypothesis_catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "hypothesis_id": "H1A",
                "family": "H1_expanded_downside_continuation",
                "priority_tier": "Tier 1",
                "source_candidate_ids": "ecb_01|ecb_02",
                "pair_scope": "ALL",
                "session_context": "London",
                "range_regime": "strongly_expanded",
                "volatility_regime": "all",
                "breach_type": "breakout_low|sweep_low",
                "breach_direction": "downside",
                "magnitude_bucket": "small|medium",
                "expected_direction": "continuation",
                "evaluation_horizon": "h4",
                "status": "primary_candidate",
            },
            {
                "hypothesis_id": "H1B",
                "family": "H1_expanded_downside_continuation",
                "priority_tier": "Tier 1",
                "source_candidate_ids": "ecb_04",
                "pair_scope": "ALL",
                "session_context": "early New York",
                "range_regime": "strongly_expanded",
                "volatility_regime": "all",
                "breach_type": "sweep_low",
                "breach_direction": "downside",
                "magnitude_bucket": "medium",
                "expected_direction": "continuation",
                "evaluation_horizon": "h4",
                "status": "primary_candidate",
            },
            {
                "hypothesis_id": "H2",
                "family": "H2_usdjpy_upside_continuation",
                "priority_tier": "Tier 2",
                "source_candidate_ids": "ecb_05",
                "pair_scope": "USDJPY",
                "session_context": "New York",
                "range_regime": "strongly_expanded",
                "volatility_regime": "all",
                "breach_type": "breakout_high",
                "breach_direction": "upside",
                "magnitude_bucket": "small",
                "expected_direction": "continuation",
                "evaluation_horizon": "h4",
                "status": "secondary_candidate",
            },
            {
                "hypothesis_id": "H3",
                "family": "H3_early_new_york_upside_sidecase",
                "priority_tier": "Tier 3",
                "source_candidate_ids": "ecb_03",
                "pair_scope": "ALL",
                "session_context": "early New York",
                "range_regime": "strongly_expanded",
                "volatility_regime": "all",
                "breach_type": "sweep_high",
                "breach_direction": "upside",
                "magnitude_bucket": "small",
                "expected_direction": "continuation",
                "evaluation_horizon": "h4",
                "status": "exploratory_candidate",
            },
        ]
    )


def test_build_experiment_catalog_keeps_small_priority_ordered_set() -> None:
    catalog = build_experiment_catalog(_hypothesis_catalog())

    assert list(catalog["experiment_id"]) == [
        "EXP_H1A_01",
        "EXP_H1A_02",
        "EXP_H1B_01",
        "EXP_H2_01",
        "EXP_H3_01",
    ]
    assert list(catalog["status"]) == [
        "planned_primary",
        "planned_primary",
        "planned_primary",
        "planned_secondary",
        "deferred",
    ]
    assert catalog.loc[catalog["experiment_id"] == "EXP_H1A_01", "pair_scope"].item() == "EURUSD|GBPUSD"
    assert catalog.loc[catalog["experiment_id"] == "EXP_H2_01", "pair_scope"].item() == "USDJPY"


def test_build_validation_ladder_exports_shared_stage_sequence() -> None:
    ladder = build_validation_ladder()

    assert list(ladder["stage_name"]) == [
        "logic_test",
        "smoke_backtest",
        "focused_sweep",
        "walk_forward",
        "cost_stress",
        "robustness",
        "portfolio_check",
    ]
    assert (ladder["stage_order"] == range(1, 8)).all()
