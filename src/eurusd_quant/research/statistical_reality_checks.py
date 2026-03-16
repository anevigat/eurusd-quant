from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from eurusd_quant.research.session_state_transitions import expected_next_session


LOW_SAMPLE_THRESHOLD = 30
MIN_TOTAL_SAMPLE_POOLED = 300
MIN_TOTAL_SAMPLE_PAIR_SPECIFIC = 180
MIN_YEARLY_SAMPLE = 25
MIN_YEARS_WITH_SAMPLE = 4
MIN_PAIR_SAMPLE_POOLED = 120
MIN_PAIR_SAMPLE_PAIR_SPECIFIC = 180
MIN_PAIRS_WITH_SIGNAL = 2
SENSITIVITY_SAMPLE_RATIO_FLOOR = 0.40
FRICTION_SANITY_PIPS = 1.0


ObservationFilter = Callable[[pd.DataFrame], pd.Series]


@dataclass(frozen=True)
class SensitivityVariant:
    variant_id: str
    description: str
    selector: ObservationFilter


@dataclass(frozen=True)
class CandidatePattern:
    pattern_id: str
    pattern_family: str
    pair_scope: str
    source_phase: str
    brief_description: str
    dataset_name: str
    outcome_col: str
    horizon_label: str
    selector: ObservationFilter
    sensitivity_variants: tuple[SensitivityVariant, ...] = field(default_factory=tuple)
    continuation_col: str | None = None
    reversal_col: str | None = None
    year_col: str = "year"


def _pip_multiplier(pair: str) -> float:
    return 100.0 if pair.endswith("JPY") else 10000.0


def _ci_bounds(mean_value: float, standard_error: float) -> tuple[float, float]:
    if pd.isna(mean_value) or pd.isna(standard_error):
        return (np.nan, np.nan)
    width = 1.96 * standard_error
    return (mean_value - width, mean_value + width)


def build_transition_observations(session_states: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    ordered = session_states.copy()
    ordered["session_start"] = pd.to_datetime(ordered["session_start"], utc=True)
    ordered["session_end"] = pd.to_datetime(ordered["session_end"], utc=True)
    ordered["session_date"] = pd.to_datetime(ordered["session_date"])
    ordered = ordered.sort_values(["pair", "session_start"]).reset_index(drop=True)

    for pair, group in ordered.groupby("pair", sort=False):
        group = group.reset_index(drop=True)
        for idx in range(len(group) - 1):
            current = group.iloc[idx]
            previous: pd.Series | None = None
            if idx > 0:
                prev_candidate = group.iloc[idx - 1]
                if current["session"] == expected_next_session(prev_candidate["session"]):
                    previous = prev_candidate
            nxt = group.iloc[idx + 1]
            if nxt["session"] != expected_next_session(current["session"]):
                continue

            current_sign = float(current["session_direction_sign"])
            next_sign = float(nxt["session_direction_sign"])
            if current_sign == 0.0 or next_sign == 0.0:
                continuation = np.nan
                reversal = np.nan
                aligned_return = np.nan
            else:
                continuation = float(current_sign == next_sign)
                reversal = float(current_sign == -next_sign)
                aligned_return = float(current_sign * float(nxt["session_return"]))

            rows.append(
                {
                    "pair": pair,
                    "transition_type": f"{current['session']}_to_{nxt['session']}",
                    "previous_session_name": previous["session"] if previous is not None else "none",
                    "previous_session_direction": previous["session_direction"] if previous is not None else "none",
                    "previous_volatility_regime": previous["volatility_regime"] if previous is not None else "unknown",
                    "previous_range_regime": previous["range_regime"] if previous is not None else "unknown",
                    "current_session_name": current["session"],
                    "next_session_name": nxt["session"],
                    "current_session_start": current["session_start"],
                    "next_session_start": nxt["session_start"],
                    "current_year": int(current["session_start"].year),
                    "next_year": int(nxt["session_start"].year),
                    "current_session_return": current["session_return"],
                    "current_session_abs_return": current["session_abs_return"],
                    "current_session_direction": current["session_direction"],
                    "current_session_direction_sign": current_sign,
                    "current_volatility_regime": current["volatility_regime"],
                    "current_range_regime": current["range_regime"],
                    "current_directional_efficiency_ratio": current["directional_efficiency_ratio"],
                    "current_close_location_value": current["close_location_value"],
                    "current_structural_breach_presence": current["structural_breach_presence"],
                    "current_breach_direction": current["breach_direction"],
                    "current_breach_magnitude_bucket": current["breach_magnitude_bucket"],
                    "current_breakout_event_count": current["breakout_event_count"],
                    "current_sweep_event_count": current["sweep_event_count"],
                    "next_session_return": nxt["session_return"],
                    "next_session_abs_return": nxt["session_abs_return"],
                    "next_session_direction": nxt["session_direction"],
                    "next_session_direction_sign": next_sign,
                    "next_volatility_regime": nxt["volatility_regime"],
                    "next_range_regime": nxt["range_regime"],
                    "next_directional_efficiency_ratio": nxt["directional_efficiency_ratio"],
                    "next_close_location_value": nxt["close_location_value"],
                    "next_structural_breach_presence": nxt["structural_breach_presence"],
                    "next_aligned_return": aligned_return,
                    "next_continuation_flag": continuation,
                    "next_reversal_flag": reversal,
                    "outcome_pip_multiplier": _pip_multiplier(pair),
                }
            )

    return pd.DataFrame(rows)


def load_reality_check_inputs(diagnostics_root: Path) -> dict[str, pd.DataFrame]:
    session_states = pd.read_csv(
        diagnostics_root / "session_state_transitions" / "session_state_inventory.csv",
        parse_dates=["session_date", "fx_session_date", "session_start", "session_end"],
    )
    session_states["year"] = session_states["session_start"].dt.year.astype(int)
    session_states["outcome_pip_multiplier"] = session_states["pair"].map(_pip_multiplier)

    contextual_inventory = pd.read_csv(
        diagnostics_root / "contextual_breaches" / "contextual_breach_inventory.csv",
        parse_dates=["timestamp", "fx_session_date"],
    )
    contextual_outcomes = pd.read_csv(diagnostics_root / "contextual_breaches" / "contextual_breach_outcomes.csv")
    contextual = contextual_inventory.merge(contextual_outcomes, on="event_id", how="inner")
    contextual["year"] = contextual["timestamp"].dt.year.astype(int)
    contextual["outcome_pip_multiplier"] = contextual["pair"].map(_pip_multiplier)

    transitions = build_transition_observations(session_states)
    return {
        "session_states": session_states,
        "transition_observations": transitions,
        "contextual_breaches": contextual,
    }


def candidate_patterns() -> tuple[CandidatePattern, ...]:
    return (
        CandidatePattern(
            pattern_id="lny_continuation_baseline",
            pattern_family="session_transition",
            pair_scope="pooled",
            source_phase="R2,R6",
            brief_description="London to New York next-session continuation across all three pairs.",
            dataset_name="transition_observations",
            outcome_col="next_aligned_return",
            continuation_col="next_continuation_flag",
            reversal_col="next_reversal_flag",
            horizon_label="next_session",
            year_col="next_year",
            selector=lambda frame: (
                (frame["transition_type"] == "london_to_new_york")
                & frame["current_session_direction"].isin(["up", "down"])
                & frame["next_session_direction"].isin(["up", "down"])
            ),
            sensitivity_variants=(
                SensitivityVariant(
                    variant_id="non_compressed_london",
                    description="Exclude compressed London states.",
                    selector=lambda frame: (
                        (frame["transition_type"] == "london_to_new_york")
                        & frame["current_session_direction"].isin(["up", "down"])
                        & frame["next_session_direction"].isin(["up", "down"])
                        & frame["current_range_regime"].isin(["normal", "expanded"])
                    ),
                ),
                SensitivityVariant(
                    variant_id="breach_present_only",
                    description="Require a London breakout or sweep to be present.",
                    selector=lambda frame: (
                        (frame["transition_type"] == "london_to_new_york")
                        & frame["current_session_direction"].isin(["up", "down"])
                        & frame["next_session_direction"].isin(["up", "down"])
                        & frame["current_structural_breach_presence"].isin(["breakout", "sweep"])
                    ),
                ),
                SensitivityVariant(
                    variant_id="medium_high_vol_only",
                    description="Restrict to medium/high-vol London states.",
                    selector=lambda frame: (
                        (frame["transition_type"] == "london_to_new_york")
                        & frame["current_session_direction"].isin(["up", "down"])
                        & frame["next_session_direction"].isin(["up", "down"])
                        & frame["current_volatility_regime"].isin(["medium_vol", "high_vol"])
                    ),
                ),
            ),
        ),
        CandidatePattern(
            pattern_id="lny_expanded_london_continuation",
            pattern_family="session_transition",
            pair_scope="pooled",
            source_phase="R5,R6",
            brief_description="Expanded London states carrying direction into the following New York session.",
            dataset_name="transition_observations",
            outcome_col="next_aligned_return",
            continuation_col="next_continuation_flag",
            reversal_col="next_reversal_flag",
            horizon_label="next_session",
            year_col="next_year",
            selector=lambda frame: (
                (frame["transition_type"] == "london_to_new_york")
                & (frame["current_range_regime"] == "expanded")
                & frame["current_session_direction"].isin(["up", "down"])
                & frame["next_session_direction"].isin(["up", "down"])
            ),
            sensitivity_variants=(
                SensitivityVariant(
                    variant_id="expanded_with_breach",
                    description="Expanded London plus a dominant breakout or sweep.",
                    selector=lambda frame: (
                        (frame["transition_type"] == "london_to_new_york")
                        & (frame["current_range_regime"] == "expanded")
                        & frame["current_session_direction"].isin(["up", "down"])
                        & frame["next_session_direction"].isin(["up", "down"])
                        & frame["current_structural_breach_presence"].isin(["breakout", "sweep"])
                    ),
                ),
                SensitivityVariant(
                    variant_id="expanded_noncompressed_prev",
                    description="Expanded London with the prior state not compressed.",
                    selector=lambda frame: (
                        (frame["transition_type"] == "london_to_new_york")
                        & (frame["current_range_regime"] == "expanded")
                        & frame["current_session_direction"].isin(["up", "down"])
                        & frame["next_session_direction"].isin(["up", "down"])
                        & frame["previous_range_regime"].isin(["normal", "expanded"])
                    ),
                ),
                SensitivityVariant(
                    variant_id="expanded_medium_high_vol",
                    description="Expanded London under medium/high volatility only.",
                    selector=lambda frame: (
                        (frame["transition_type"] == "london_to_new_york")
                        & (frame["current_range_regime"] == "expanded")
                        & frame["current_session_direction"].isin(["up", "down"])
                        & frame["next_session_direction"].isin(["up", "down"])
                        & frame["current_volatility_regime"].isin(["medium_vol", "high_vol"])
                    ),
                ),
            ),
        ),
        CandidatePattern(
            pattern_id="expanded_contextual_breaches_h4",
            pattern_family="contextual_breach",
            pair_scope="pooled",
            source_phase="R4,R5",
            brief_description="Expanded-range structural breaches, evaluated on +4-bar aligned post-breach returns.",
            dataset_name="contextual_breaches",
            outcome_col="aligned_forward_return_4",
            continuation_col="continuation_flag_4",
            reversal_col="reversal_flag_4",
            horizon_label="+4_bars",
            selector=lambda frame: frame["range_regime"] == "expanded",
            sensitivity_variants=(
                SensitivityVariant(
                    variant_id="expanded_breakouts_only",
                    description="Expanded-range breakouts only.",
                    selector=lambda frame: (frame["range_regime"] == "expanded") & (frame["event_class"] == "breakout"),
                ),
                SensitivityVariant(
                    variant_id="expanded_sweeps_only",
                    description="Expanded-range sweeps only.",
                    selector=lambda frame: (frame["range_regime"] == "expanded") & (frame["event_class"] == "sweep"),
                ),
                SensitivityVariant(
                    variant_id="expanded_48_96_window",
                    description="Expanded-range breaches on 48/96-bar structural windows only.",
                    selector=lambda frame: (frame["range_regime"] == "expanded") & frame["lookback_window"].isin([48, 96]),
                ),
            ),
        ),
        CandidatePattern(
            pattern_id="usdjpy_expanded_up_lny",
            pattern_family="session_transition",
            pair_scope="USDJPY",
            source_phase="R5,R6",
            brief_description="USDJPY expanded-up London states carrying into the next New York session.",
            dataset_name="transition_observations",
            outcome_col="next_aligned_return",
            continuation_col="next_continuation_flag",
            reversal_col="next_reversal_flag",
            horizon_label="next_session",
            year_col="next_year",
            selector=lambda frame: (
                (frame["pair"] == "USDJPY")
                & (frame["transition_type"] == "london_to_new_york")
                & (frame["current_range_regime"] == "expanded")
                & (frame["current_session_direction"] == "up")
                & frame["next_session_direction"].isin(["up", "down"])
            ),
            sensitivity_variants=(
                SensitivityVariant(
                    variant_id="usdjpy_expanded_up_breakout",
                    description="USDJPY expanded-up London states with dominant breakout structure.",
                    selector=lambda frame: (
                        (frame["pair"] == "USDJPY")
                        & (frame["transition_type"] == "london_to_new_york")
                        & (frame["current_range_regime"] == "expanded")
                        & (frame["current_session_direction"] == "up")
                        & (frame["current_structural_breach_presence"] == "breakout")
                        & frame["next_session_direction"].isin(["up", "down"])
                    ),
                ),
                SensitivityVariant(
                    variant_id="usdjpy_expanded_up_sweep",
                    description="USDJPY expanded-up London states with dominant sweep structure.",
                    selector=lambda frame: (
                        (frame["pair"] == "USDJPY")
                        & (frame["transition_type"] == "london_to_new_york")
                        & (frame["current_range_regime"] == "expanded")
                        & (frame["current_session_direction"] == "up")
                        & (frame["current_structural_breach_presence"] == "sweep")
                        & frame["next_session_direction"].isin(["up", "down"])
                    ),
                ),
                SensitivityVariant(
                    variant_id="usdjpy_expanded_up_medium_high_vol",
                    description="USDJPY expanded-up London states under medium/high volatility.",
                    selector=lambda frame: (
                        (frame["pair"] == "USDJPY")
                        & (frame["transition_type"] == "london_to_new_york")
                        & (frame["current_range_regime"] == "expanded")
                        & (frame["current_session_direction"] == "up")
                        & (frame["current_volatility_regime"].isin(["medium_vol", "high_vol"]))
                        & frame["next_session_direction"].isin(["up", "down"])
                    ),
                ),
            ),
        ),
        CandidatePattern(
            pattern_id="low_vol_new_york_bias",
            pattern_family="session_regime",
            pair_scope="pooled",
            source_phase="R2,R3",
            brief_description="Low-volatility New York sessions with positive-close bias.",
            dataset_name="session_states",
            outcome_col="session_return",
            horizon_label="same_session",
            selector=lambda frame: (frame["session"] == "new_york") & (frame["volatility_regime"] == "low_vol"),
            sensitivity_variants=(
                SensitivityVariant(
                    variant_id="low_medium_vol_new_york",
                    description="Low/medium-volatility New York sessions.",
                    selector=lambda frame: (frame["session"] == "new_york")
                    & frame["volatility_regime"].isin(["low_vol", "medium_vol"]),
                ),
                SensitivityVariant(
                    variant_id="low_vol_new_york_nonexpanded",
                    description="Low-volatility New York sessions outside expanded range states.",
                    selector=lambda frame: (
                        (frame["session"] == "new_york")
                        & (frame["volatility_regime"] == "low_vol")
                        & frame["range_regime"].isin(["compressed", "normal"])
                    ),
                ),
                SensitivityVariant(
                    variant_id="low_vol_new_york_european_pairs",
                    description="Low-volatility New York sessions on EURUSD/GBPUSD only.",
                    selector=lambda frame: (
                        (frame["session"] == "new_york")
                        & (frame["volatility_regime"] == "low_vol")
                        & frame["pair"].isin(["EURUSD", "GBPUSD"])
                    ),
                ),
            ),
        ),
    )


def evaluate_pattern_observations(
    observations: pd.DataFrame,
    *,
    outcome_col: str,
    continuation_col: str | None = None,
    reversal_col: str | None = None,
) -> dict[str, Any]:
    usable = observations.dropna(subset=[outcome_col]).copy()
    sample_count = int(len(usable))
    if sample_count == 0:
        return {
            "sample_count": 0,
            "mean_outcome": np.nan,
            "median_outcome": np.nan,
            "positive_fraction": np.nan,
            "continuation_fraction": np.nan,
            "reversal_fraction": np.nan,
            "outcome_std": np.nan,
            "outcome_se": np.nan,
            "ci_lower": np.nan,
            "ci_upper": np.nan,
            "mean_outcome_pips": np.nan,
            "friction_survives_1pip": False,
        }

    outcome = usable[outcome_col].astype(float)
    standard_error = float(outcome.std(ddof=1) / np.sqrt(sample_count)) if sample_count > 1 else np.nan
    ci_lower, ci_upper = _ci_bounds(float(outcome.mean()), standard_error)
    result: dict[str, Any] = {
        "sample_count": sample_count,
        "mean_outcome": float(outcome.mean()),
        "median_outcome": float(outcome.median()),
        "positive_fraction": float((outcome > 0).mean()),
        "continuation_fraction": float(usable[continuation_col].mean()) if continuation_col else np.nan,
        "reversal_fraction": float(usable[reversal_col].mean()) if reversal_col else np.nan,
        "outcome_std": float(outcome.std(ddof=1)) if sample_count > 1 else np.nan,
        "outcome_se": standard_error,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
    }
    mean_outcome_pips = float((outcome * usable["outcome_pip_multiplier"].astype(float)).mean())
    result["mean_outcome_pips"] = mean_outcome_pips
    result["friction_survives_1pip"] = abs(mean_outcome_pips) > FRICTION_SANITY_PIPS
    return result


def summarize_yearly_stability(
    pattern: CandidatePattern,
    observations: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    year_rows: list[dict[str, Any]] = []
    if observations.empty:
        return pd.DataFrame(columns=["pattern_id", "year"]), {
            "years_with_min_sample": 0,
            "positive_years": 0,
            "negative_years": 0,
            "largest_year_share": np.nan,
        }

    grouped = observations.groupby(pattern.year_col, dropna=False)
    yearly_contrib: list[float] = []
    positive_years = 0
    negative_years = 0
    years_with_min_sample = 0

    for year, frame in grouped:
        metrics = evaluate_pattern_observations(
            frame,
            outcome_col=pattern.outcome_col,
            continuation_col=pattern.continuation_col,
            reversal_col=pattern.reversal_col,
        )
        row = {"pattern_id": pattern.pattern_id, "year": int(year), **metrics}
        row["passes_min_year_sample"] = metrics["sample_count"] >= MIN_YEARLY_SAMPLE
        if row["passes_min_year_sample"]:
            years_with_min_sample += 1
        if pd.notna(metrics["mean_outcome"]) and metrics["mean_outcome"] > 0:
            positive_years += 1
        elif pd.notna(metrics["mean_outcome"]) and metrics["mean_outcome"] < 0:
            negative_years += 1
        yearly_contrib.append(abs(float(frame[pattern.outcome_col].dropna().sum())))
        year_rows.append(row)

    denom = float(sum(yearly_contrib))
    largest_year_share = (max(yearly_contrib) / denom) if denom > 0 else np.nan
    diagnostics = {
        "years_with_min_sample": years_with_min_sample,
        "positive_years": positive_years,
        "negative_years": negative_years,
        "largest_year_share": largest_year_share,
    }
    return pd.DataFrame(year_rows), diagnostics


def summarize_pair_stability(
    pattern: CandidatePattern,
    observations: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    pair_rows: list[dict[str, Any]] = []
    if observations.empty:
        return pd.DataFrame(columns=["pattern_id", "pair"]), {
            "pairs_with_min_sample": 0,
            "pairs_positive": 0,
            "mean_outcome_variance": np.nan,
        }

    pair_means: list[float] = []
    pairs_with_min_sample = 0
    pairs_positive = 0
    for pair, frame in observations.groupby("pair", dropna=False):
        metrics = evaluate_pattern_observations(
            frame,
            outcome_col=pattern.outcome_col,
            continuation_col=pattern.continuation_col,
            reversal_col=pattern.reversal_col,
        )
        row = {"pattern_id": pattern.pattern_id, "pair": pair, **metrics}
        row["passes_min_pair_sample"] = metrics["sample_count"] >= (
            MIN_PAIR_SAMPLE_PAIR_SPECIFIC if pattern.pair_scope != "pooled" else MIN_PAIR_SAMPLE_POOLED
        )
        if row["passes_min_pair_sample"]:
            pairs_with_min_sample += 1
        if pd.notna(metrics["mean_outcome"]) and metrics["mean_outcome"] > 0:
            pairs_positive += 1
        pair_means.append(float(metrics["mean_outcome"]))
        pair_rows.append(row)

    diagnostics = {
        "pairs_with_min_sample": pairs_with_min_sample,
        "pairs_positive": pairs_positive,
        "mean_outcome_variance": float(np.nanvar(pair_means, ddof=0)),
    }
    return pd.DataFrame(pair_rows), diagnostics


def summarize_sensitivity(
    pattern: CandidatePattern,
    source_frame: pd.DataFrame,
    *,
    base_sample_count: int,
    base_mean_outcome: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sign_consistent = True
    sample_consistent = True

    for variant in pattern.sensitivity_variants:
        mask = variant.selector(source_frame)
        metrics = evaluate_pattern_observations(
            source_frame[mask],
            outcome_col=pattern.outcome_col,
            continuation_col=pattern.continuation_col,
            reversal_col=pattern.reversal_col,
        )
        sign_matches = (
            pd.notna(metrics["mean_outcome"])
            and pd.notna(base_mean_outcome)
            and np.sign(metrics["mean_outcome"]) == np.sign(base_mean_outcome)
        )
        if not sign_matches:
            sign_consistent = False
        sample_ratio = metrics["sample_count"] / base_sample_count if base_sample_count else np.nan
        if pd.notna(sample_ratio) and sample_ratio < SENSITIVITY_SAMPLE_RATIO_FLOOR:
            sample_consistent = False
        rows.append(
            {
                "pattern_id": pattern.pattern_id,
                "variant_id": variant.variant_id,
                "description": variant.description,
                "sample_ratio_to_base": sample_ratio,
                "sign_matches_base": sign_matches,
                **metrics,
            }
        )

    return pd.DataFrame(rows), {
        "sensitivity_sign_consistent": sign_consistent,
        "sensitivity_sample_consistent": sample_consistent,
    }


def sample_filter_summary(
    pattern: CandidatePattern,
    *,
    base_sample_count: int,
    years_with_min_sample: int,
    pairs_with_min_sample: int,
) -> dict[str, Any]:
    min_total = MIN_TOTAL_SAMPLE_POOLED if pattern.pair_scope == "pooled" else MIN_TOTAL_SAMPLE_PAIR_SPECIFIC
    min_pair = MIN_PAIR_SAMPLE_POOLED if pattern.pair_scope == "pooled" else MIN_PAIR_SAMPLE_PAIR_SPECIFIC
    required_pairs = MIN_PAIRS_WITH_SIGNAL if pattern.pair_scope == "pooled" else 1
    return {
        "pattern_id": pattern.pattern_id,
        "pair_scope": pattern.pair_scope,
        "base_sample_count": base_sample_count,
        "min_total_sample": min_total,
        "passes_total_sample": base_sample_count >= min_total,
        "min_yearly_sample": MIN_YEARLY_SAMPLE,
        "years_with_min_sample": years_with_min_sample,
        "min_year_buckets": MIN_YEARS_WITH_SAMPLE,
        "passes_yearly_sample": years_with_min_sample >= MIN_YEARS_WITH_SAMPLE,
        "min_pair_sample": min_pair,
        "pairs_with_min_sample": pairs_with_min_sample,
        "required_pairs_with_signal": required_pairs,
        "passes_pair_sample": pairs_with_min_sample >= required_pairs,
    }


def assign_credibility_label(
    pattern: CandidatePattern,
    base_metrics: dict[str, Any],
    sample_filters: dict[str, Any],
    yearly_diagnostics: dict[str, Any],
    pair_diagnostics: dict[str, Any],
    sensitivity_diagnostics: dict[str, Any],
) -> tuple[str, str]:
    if not sample_filters["passes_total_sample"] or not sample_filters["passes_yearly_sample"]:
        return ("fragile", "insufficient total sample or year-by-year coverage")
    if pd.notna(yearly_diagnostics["largest_year_share"]) and yearly_diagnostics["largest_year_share"] > 0.45:
        return ("fragile", "effect is overly concentrated in one year")
    if pd.isna(base_metrics["mean_outcome"]) or base_metrics["mean_outcome"] <= 0:
        return ("descriptive_only", "effect does not retain a positive aligned mean outcome in the base definition")
    if yearly_diagnostics["positive_years"] <= yearly_diagnostics["negative_years"]:
        return ("descriptive_only", "positive years do not outnumber negative years")
    if not sensitivity_diagnostics["sensitivity_sign_consistent"]:
        return ("fragile", "effect changes sign under nearby definition changes")
    if not sensitivity_diagnostics["sensitivity_sample_consistent"]:
        return ("descriptive_only", "effect survives only after large sample collapse in sensitivity checks")

    multi_pair_support = pair_diagnostics["pairs_positive"] >= MIN_PAIRS_WITH_SIGNAL
    if pattern.pair_scope == "pooled":
        if sample_filters["passes_pair_sample"] and multi_pair_support and base_metrics["friction_survives_1pip"]:
            return ("credible_candidate_for_hypothesis", "multi-pair support, stable years, and simple friction sanity")
        return ("descriptive_only", "pooled pattern is visible, but not robust enough across pairs or friction sanity")

    if sample_filters["passes_pair_sample"] and base_metrics["friction_survives_1pip"]:
        return ("pair_specific_candidate", "pair-specific effect survives sample, stability, and friction sanity")
    return ("descriptive_only", "pair-specific effect is interesting but not strong enough to survive all filters")


def build_candidate_inventory(
    patterns: tuple[CandidatePattern, ...],
    frames: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for pattern in patterns:
        source_frame = frames[pattern.dataset_name]
        base_frame = source_frame[pattern.selector(source_frame)].copy()
        rows.append(
            {
                "pattern_id": pattern.pattern_id,
                "pattern_family": pattern.pattern_family,
                "pair_scope": pattern.pair_scope,
                "source_phase": pattern.source_phase,
                "brief_description": pattern.brief_description,
                "base_sample_count": int(base_frame[pattern.outcome_col].notna().sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(["pattern_family", "pattern_id"]).reset_index(drop=True)


def run_reality_checks(diagnostics_root: Path) -> dict[str, pd.DataFrame | dict[str, Any]]:
    frames = load_reality_check_inputs(diagnostics_root)
    patterns = candidate_patterns()

    candidate_inventory = build_candidate_inventory(patterns, frames)
    reality_rows: list[dict[str, Any]] = []
    yearly_tables: list[pd.DataFrame] = []
    pair_tables: list[pd.DataFrame] = []
    sensitivity_tables: list[pd.DataFrame] = []
    sample_filter_rows: list[dict[str, Any]] = []

    for pattern in patterns:
        source_frame = frames[pattern.dataset_name]
        base_frame = source_frame[pattern.selector(source_frame)].copy()
        base_metrics = evaluate_pattern_observations(
            base_frame,
            outcome_col=pattern.outcome_col,
            continuation_col=pattern.continuation_col,
            reversal_col=pattern.reversal_col,
        )
        yearly_df, yearly_diag = summarize_yearly_stability(pattern, base_frame)
        pair_df, pair_diag = summarize_pair_stability(pattern, base_frame)
        sensitivity_df, sensitivity_diag = summarize_sensitivity(
            pattern,
            source_frame,
            base_sample_count=base_metrics["sample_count"],
            base_mean_outcome=base_metrics["mean_outcome"],
        )
        sample_filters = sample_filter_summary(
            pattern,
            base_sample_count=base_metrics["sample_count"],
            years_with_min_sample=yearly_diag["years_with_min_sample"],
            pairs_with_min_sample=pair_diag["pairs_with_min_sample"],
        )
        label, label_reason = assign_credibility_label(
            pattern,
            base_metrics,
            sample_filters,
            yearly_diag,
            pair_diag,
            sensitivity_diag,
        )

        yearly_tables.append(yearly_df)
        pair_tables.append(pair_df)
        sensitivity_tables.append(sensitivity_df)
        sample_filter_rows.append(sample_filters)
        reality_rows.append(
            {
                "pattern_id": pattern.pattern_id,
                "pattern_family": pattern.pattern_family,
                "pair_scope": pattern.pair_scope,
                "source_phase": pattern.source_phase,
                "brief_description": pattern.brief_description,
                "horizon_label": pattern.horizon_label,
                **base_metrics,
                **yearly_diag,
                **pair_diag,
                **sensitivity_diag,
                "credibility_label": label,
                "label_reason": label_reason,
            }
        )

    notes = {
        "sample_thresholds": {
            "low_sample_threshold": LOW_SAMPLE_THRESHOLD,
            "min_total_sample_pooled": MIN_TOTAL_SAMPLE_POOLED,
            "min_total_sample_pair_specific": MIN_TOTAL_SAMPLE_PAIR_SPECIFIC,
            "min_yearly_sample": MIN_YEARLY_SAMPLE,
            "min_year_buckets": MIN_YEARS_WITH_SAMPLE,
            "min_pair_sample_pooled": MIN_PAIR_SAMPLE_POOLED,
            "min_pair_sample_pair_specific": MIN_PAIR_SAMPLE_PAIR_SPECIFIC,
            "sensitivity_sample_ratio_floor": SENSITIVITY_SAMPLE_RATIO_FLOOR,
            "friction_sanity_pips": FRICTION_SANITY_PIPS,
        },
        "candidate_pattern_count": len(patterns),
    }
    return {
        "candidate_patterns": candidate_inventory,
        "reality_check_summary": pd.DataFrame(reality_rows).sort_values("pattern_id").reset_index(drop=True),
        "yearly_stability_summary": pd.concat(yearly_tables, ignore_index=True).sort_values(["pattern_id", "year"]),
        "pair_stability_summary": pd.concat(pair_tables, ignore_index=True).sort_values(["pattern_id", "pair"]),
        "sensitivity_summary": pd.concat(sensitivity_tables, ignore_index=True).sort_values(
            ["pattern_id", "variant_id"]
        ),
        "sample_size_filter_summary": pd.DataFrame(sample_filter_rows).sort_values("pattern_id").reset_index(
            drop=True
        ),
        "statistical_reality_notes": notes,
    }
