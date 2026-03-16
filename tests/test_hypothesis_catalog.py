from __future__ import annotations

import pandas as pd

from eurusd_quant.research.hypothesis_catalog import (
    build_hypothesis_catalog,
    build_hypothesis_priority_summary,
)


def _edge_candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "candidate_id": "ecb_01",
                "pair_scope": "ALL",
                "session_context": "London",
                "range_regime": "strongly_expanded",
                "breach_type": "breakout_low",
                "magnitude_bucket": "small",
                "evaluation_horizon": "h4",
                "sample_count": 596,
            },
            {
                "candidate_id": "ecb_02",
                "pair_scope": "ALL",
                "session_context": "London",
                "range_regime": "strongly_expanded",
                "breach_type": "sweep_low",
                "magnitude_bucket": "medium",
                "evaluation_horizon": "h4",
                "sample_count": 485,
            },
            {
                "candidate_id": "ecb_03",
                "pair_scope": "ALL",
                "session_context": "early New York",
                "range_regime": "strongly_expanded",
                "breach_type": "sweep_high",
                "magnitude_bucket": "small",
                "evaluation_horizon": "h4",
                "sample_count": 547,
            },
            {
                "candidate_id": "ecb_04",
                "pair_scope": "ALL",
                "session_context": "early New York",
                "range_regime": "strongly_expanded",
                "breach_type": "sweep_low",
                "magnitude_bucket": "medium",
                "evaluation_horizon": "h4",
                "sample_count": 575,
            },
            {
                "candidate_id": "ecb_05",
                "pair_scope": "USDJPY",
                "session_context": "New York",
                "range_regime": "strongly_expanded",
                "breach_type": "breakout_high",
                "magnitude_bucket": "small",
                "evaluation_horizon": "h4",
                "sample_count": 722,
            },
        ]
    )


def test_build_hypothesis_catalog_groups_candidates_into_expected_families() -> None:
    catalog = build_hypothesis_catalog(_edge_candidates())

    assert list(catalog["hypothesis_id"]) == ["H1A", "H1B", "H2", "H3"]
    assert catalog.loc[catalog["hypothesis_id"] == "H1A", "source_candidate_ids"].item() == "ecb_01|ecb_02"
    assert catalog.loc[catalog["hypothesis_id"] == "H2", "pair_scope"].item() == "USDJPY"
    assert catalog.loc[catalog["hypothesis_id"] == "H3", "status"].item() == "exploratory_candidate"


def test_build_hypothesis_priority_summary_preserves_tier_order_and_samples() -> None:
    catalog = build_hypothesis_catalog(_edge_candidates())
    summary = build_hypothesis_priority_summary(catalog)

    assert list(summary["priority_tier"]) == ["Tier 1", "Tier 1", "Tier 2", "Tier 3"]
    assert summary.loc[summary["hypothesis_id"] == "H1A", "base_sample_count"].item() == 1081
    assert summary.loc[summary["hypothesis_id"] == "H2", "expected_horizon"].item() == "h4"
