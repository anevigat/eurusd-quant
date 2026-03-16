from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_edge_candidates(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "candidate_id",
        "pair_scope",
        "session_context",
        "range_regime",
        "breach_type",
        "magnitude_bucket",
        "evaluation_horizon",
        "sample_count",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"edge candidate file is missing required columns: {sorted(missing)}")
    return frame


def build_hypothesis_catalog(edge_candidates: pd.DataFrame) -> pd.DataFrame:
    edge_by_id = edge_candidates.set_index("candidate_id")
    required_ids = {"ecb_01", "ecb_02", "ecb_03", "ecb_04", "ecb_05"}
    missing_ids = required_ids.difference(edge_by_id.index)
    if missing_ids:
        raise ValueError(f"edge candidate file is missing expected candidate ids: {sorted(missing_ids)}")

    rows = [
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
            "notes": "Primary pooled London downside continuation family built from the strongest R8 London slices.",
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
            "notes": "Secondary Tier 1 branch of the pooled downside family, focused on early New York follow-through after downside sweeps.",
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
            "notes": "Pair-specific exploratory branch retained because USDJPY continues to carry upside state more cleanly than the European pairs.",
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
            "notes": "Distinct upside side case preserved as exploratory only; it should not displace the main downside family.",
        },
    ]

    catalog = pd.DataFrame(rows)
    catalog["base_sample_count"] = catalog["source_candidate_ids"].apply(
        lambda ids: int(sum(edge_by_id.loc[candidate_id, "sample_count"] for candidate_id in ids.split("|")))
    )
    return catalog


def build_hypothesis_priority_summary(catalog: pd.DataFrame) -> pd.DataFrame:
    summary = catalog[
        [
            "hypothesis_id",
            "family",
            "priority_tier",
            "source_candidate_ids",
            "pair_scope",
            "expected_direction",
            "evaluation_horizon",
            "status",
            "notes",
            "base_sample_count",
        ]
    ].rename(columns={"evaluation_horizon": "expected_horizon"})
    return summary.sort_values(["priority_tier", "hypothesis_id"]).reset_index(drop=True)
