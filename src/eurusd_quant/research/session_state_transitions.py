from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from eurusd_quant.analytics.session_structure import build_session_records
from eurusd_quant.analytics.volatility_regimes import assign_time_aware_volatility_regimes
from eurusd_quant.research.contextual_breaches import build_bar_context, build_contextual_breach_inventory


SESSION_SEQUENCE = ("asia", "london", "new_york")
SESSION_DIRECTION_FLAT_THRESHOLD = 1e-6
LOW_SAMPLE_THRESHOLD = 30


def classify_session_direction(
    session_return: pd.Series,
    *,
    flat_threshold: float = SESSION_DIRECTION_FLAT_THRESHOLD,
) -> tuple[pd.Series, pd.Series]:
    if flat_threshold < 0:
        raise ValueError("flat_threshold must be non-negative")
    signs = np.where(
        session_return.abs() <= flat_threshold,
        0.0,
        np.where(session_return > 0, 1.0, -1.0),
    )
    labels = np.where(signs > 0, "up", np.where(signs < 0, "down", "flat"))
    return pd.Series(labels, index=session_return.index), pd.Series(signs, index=session_return.index, dtype=float)


def expected_next_session(session_name: str) -> str:
    if session_name not in SESSION_SEQUENCE:
        raise ValueError(f"Unsupported session name: {session_name!r}")
    idx = SESSION_SEQUENCE.index(session_name)
    return SESSION_SEQUENCE[(idx + 1) % len(SESSION_SEQUENCE)]


def _dominant_session_breach(inventory: pd.DataFrame) -> pd.DataFrame:
    if inventory.empty:
        return pd.DataFrame(
            columns=[
                "pair",
                "fx_session_date",
                "session",
                "structural_breach_presence",
                "breach_direction",
                "breach_magnitude_bucket",
                "breakout_event_count",
                "sweep_event_count",
                "breach_event_count",
            ]
        )

    counts = (
        inventory.groupby(["pair", "fx_session_date", "session", "event_class"], dropna=False)
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    dominant = (
        inventory.sort_values(
            ["pair", "fx_session_date", "session", "breach_magnitude_atr"],
            ascending=[True, True, True, False],
            na_position="last",
        )
        .groupby(["pair", "fx_session_date", "session"], as_index=False)
        .first()
    )
    summary = dominant[
        [
            "pair",
            "fx_session_date",
            "session",
            "event_class",
            "direction",
            "magnitude_bucket",
        ]
    ].rename(
        columns={
            "event_class": "structural_breach_presence",
            "direction": "breach_direction",
            "magnitude_bucket": "breach_magnitude_bucket",
        }
    )
    summary = summary.merge(counts, on=["pair", "fx_session_date", "session"], how="left")
    summary["breakout_event_count"] = summary.get("breakout", 0)
    summary["sweep_event_count"] = summary.get("sweep", 0)
    summary["breach_event_count"] = summary["breakout_event_count"] + summary["sweep_event_count"]
    keep_cols = [
        "pair",
        "fx_session_date",
        "session",
        "structural_breach_presence",
        "breach_direction",
        "breach_magnitude_bucket",
        "breakout_event_count",
        "sweep_event_count",
        "breach_event_count",
    ]
    return summary[keep_cols]


def build_session_state_inventory(
    bars: pd.DataFrame,
    *,
    pair: str,
    lookback_sessions: int = 120,
    min_history: int = 30,
) -> pd.DataFrame:
    context_bars = build_bar_context(
        bars,
        pair=pair,
        lookback_sessions=lookback_sessions,
        min_history=min_history,
    )
    session_records = build_session_records(bars, pair=pair)
    session_records = assign_time_aware_volatility_regimes(
        session_records,
        metric_col="realized_vol",
        lookback_sessions=lookback_sessions,
        min_history=min_history,
    )
    session_records["session_range"] = session_records["session_range_return"]
    session_records["session_date"] = session_records["fx_session_date"]

    direction_label, direction_sign = classify_session_direction(session_records["session_return"])
    session_records["session_direction"] = direction_label
    session_records["session_direction_sign"] = direction_sign

    range_lookup = (
        context_bars.groupby(["pair", "fx_session_date", "session"], dropna=False)["range_regime"]
        .first()
        .reset_index()
    )
    inventory, _ = build_contextual_breach_inventory(context_bars, pair=pair)
    breach_summary = _dominant_session_breach(inventory)

    session_states = (
        session_records.merge(range_lookup, on=["pair", "fx_session_date", "session"], how="left")
        .merge(breach_summary, on=["pair", "fx_session_date", "session"], how="left")
        .sort_values(["pair", "session_start"])
        .reset_index(drop=True)
    )
    session_states["range_regime"] = session_states["range_regime"].fillna("unknown")
    session_states["structural_breach_presence"] = session_states["structural_breach_presence"].fillna("none")
    session_states["breach_direction"] = session_states["breach_direction"].fillna("none")
    session_states["breach_magnitude_bucket"] = session_states["breach_magnitude_bucket"].fillna("none")
    for col in ("breakout_event_count", "sweep_event_count", "breach_event_count"):
        session_states[col] = session_states[col].fillna(0).astype(int)
    return session_states[
        [
            "pair",
            "session_date",
            "fx_session_date",
            "session",
            "session_start",
            "session_end",
            "session_return",
            "session_abs_return",
            "session_range",
            "session_direction",
            "session_direction_sign",
            "volatility_regime",
            "range_regime",
            "directional_efficiency_ratio",
            "close_location_value",
            "structural_breach_presence",
            "breach_direction",
            "breach_magnitude_bucket",
            "breakout_event_count",
            "sweep_event_count",
            "breach_event_count",
        ]
    ]


def build_two_session_transitions(session_states: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    ordered = session_states.sort_values(["pair", "session_start"]).reset_index(drop=True)
    for pair, group in ordered.groupby("pair", sort=False):
        group = group.reset_index(drop=True)
        for idx in range(1, len(group)):
            previous = group.iloc[idx - 1]
            current = group.iloc[idx]
            if current["session"] != expected_next_session(previous["session"]):
                continue

            previous_sign = previous["session_direction_sign"]
            current_sign = current["session_direction_sign"]
            if previous_sign == 0 or current_sign == 0:
                continuation = np.nan
                reversal = np.nan
                aligned_return = np.nan
            else:
                continuation = float(previous_sign == current_sign)
                reversal = float(previous_sign == -current_sign)
                aligned_return = float(previous_sign * current["session_return"])

            rows.append(
                {
                    "pair": pair,
                    "transition_type": f"{previous['session']}_to_{current['session']}",
                    "previous_session_name": previous["session"],
                    "current_session_name": current["session"],
                    "previous_session_direction": previous["session_direction"],
                    "current_session_direction": current["session_direction"],
                    "previous_volatility_regime": previous["volatility_regime"],
                    "current_volatility_regime": current["volatility_regime"],
                    "previous_range_regime": previous["range_regime"],
                    "current_range_regime": current["range_regime"],
                    "previous_structural_breach_presence": previous["structural_breach_presence"],
                    "current_structural_breach_presence": current["structural_breach_presence"],
                    "current_breach_direction": current["breach_direction"],
                    "current_breach_magnitude_bucket": current["breach_magnitude_bucket"],
                    "current_session_return": current["session_return"],
                    "current_session_abs_return": current["session_abs_return"],
                    "current_directional_efficiency_ratio": current["directional_efficiency_ratio"],
                    "current_close_location_value": current["close_location_value"],
                    "current_aligned_return_vs_previous": aligned_return,
                    "continuation_flag": continuation,
                    "reversal_flag": reversal,
                }
            )
    return pd.DataFrame(rows)


def build_three_session_patterns(session_states: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    ordered = session_states.sort_values(["pair", "session_start"]).reset_index(drop=True)
    for pair, group in ordered.groupby("pair", sort=False):
        group = group.reset_index(drop=True)
        for idx in range(2, len(group)):
            previous = group.iloc[idx - 2]
            current = group.iloc[idx - 1]
            nxt = group.iloc[idx]
            if current["session"] != expected_next_session(previous["session"]):
                continue
            if nxt["session"] != expected_next_session(current["session"]):
                continue

            current_sign = current["session_direction_sign"]
            next_sign = nxt["session_direction_sign"]
            if current_sign == 0 or next_sign == 0:
                next_continuation = np.nan
                next_reversal = np.nan
                next_aligned_return = np.nan
            else:
                next_continuation = float(current_sign == next_sign)
                next_reversal = float(current_sign == -next_sign)
                next_aligned_return = float(current_sign * nxt["session_return"])

            pattern_key = (
                f"{previous['session']}:{previous['range_regime']}:{previous['session_direction']}"
                f"->{current['session']}:{current['range_regime']}:{current['session_direction']}"
                f":{current['structural_breach_presence']}"
            )
            rows.append(
                {
                    "pair": pair,
                    "transition_type": f"{previous['session']}_to_{current['session']}",
                    "previous_session_name": previous["session"],
                    "current_session_name": current["session"],
                    "next_session_name": nxt["session"],
                    "previous_range_regime": previous["range_regime"],
                    "previous_session_direction": previous["session_direction"],
                    "current_range_regime": current["range_regime"],
                    "current_session_direction": current["session_direction"],
                    "current_volatility_regime": current["volatility_regime"],
                    "current_structural_breach_presence": current["structural_breach_presence"],
                    "current_breach_direction": current["breach_direction"],
                    "current_breach_magnitude_bucket": current["breach_magnitude_bucket"],
                    "pattern_key": pattern_key,
                    "next_session_return": nxt["session_return"],
                    "next_session_abs_return": nxt["session_abs_return"],
                    "next_session_direction": nxt["session_direction"],
                    "next_directional_efficiency_ratio": nxt["directional_efficiency_ratio"],
                    "next_close_location_value": nxt["close_location_value"],
                    "next_aligned_return_vs_current": next_aligned_return,
                    "next_continuation_flag": next_continuation,
                    "next_reversal_flag": next_reversal,
                }
            )
    return pd.DataFrame(rows)


def summarize_two_session_transitions(transitions: pd.DataFrame) -> pd.DataFrame:
    summary = (
        transitions.groupby(
            [
                "pair",
                "transition_type",
                "previous_session_name",
                "current_session_name",
                "previous_session_direction",
                "current_session_direction",
                "previous_volatility_regime",
                "current_volatility_regime",
                "previous_range_regime",
                "current_range_regime",
            ],
            dropna=False,
        )
        .agg(
            avg_current_return=("current_session_return", "mean"),
            avg_current_abs_return=("current_session_abs_return", "mean"),
            avg_current_efficiency=("current_directional_efficiency_ratio", "mean"),
            avg_current_clv=("current_close_location_value", "mean"),
            mean_aligned_current_return=("current_aligned_return_vs_previous", "mean"),
            continuation_fraction=("continuation_flag", "mean"),
            reversal_fraction=("reversal_flag", "mean"),
            sample_count=("current_session_return", "size"),
        )
        .reset_index()
    )
    summary["low_sample"] = summary["sample_count"] < LOW_SAMPLE_THRESHOLD
    return summary.sort_values(
        [
            "pair",
            "transition_type",
            "previous_session_direction",
            "current_session_direction",
            "previous_volatility_regime",
            "current_volatility_regime",
            "previous_range_regime",
            "current_range_regime",
        ]
    ).reset_index(drop=True)


def summarize_three_session_patterns(patterns: pd.DataFrame) -> pd.DataFrame:
    summary = (
        patterns.groupby(
            [
                "pair",
                "transition_type",
                "previous_session_name",
                "current_session_name",
                "next_session_name",
                "previous_range_regime",
                "previous_session_direction",
                "current_range_regime",
                "current_session_direction",
                "current_structural_breach_presence",
                "pattern_key",
            ],
            dropna=False,
        )
        .agg(sample_count=("pattern_key", "size"))
        .reset_index()
    )
    summary["low_sample"] = summary["sample_count"] < LOW_SAMPLE_THRESHOLD
    return summary.sort_values(["pair", "transition_type", "sample_count"], ascending=[True, True, False]).reset_index(
        drop=True
    )


def summarize_next_session_outcomes(patterns: pd.DataFrame) -> pd.DataFrame:
    summary = (
        patterns.groupby(
            [
                "pair",
                "transition_type",
                "previous_session_name",
                "current_session_name",
                "next_session_name",
                "previous_range_regime",
                "previous_session_direction",
                "current_range_regime",
                "current_session_direction",
                "current_structural_breach_presence",
                "pattern_key",
            ],
            dropna=False,
        )
        .agg(
            avg_next_session_return=("next_session_return", "mean"),
            avg_next_session_abs_return=("next_session_abs_return", "mean"),
            avg_next_directional_efficiency=("next_directional_efficiency_ratio", "mean"),
            avg_next_clv=("next_close_location_value", "mean"),
            mean_aligned_next_return=("next_aligned_return_vs_current", "mean"),
            continuation_fraction=("next_continuation_flag", "mean"),
            reversal_fraction=("next_reversal_flag", "mean"),
            sample_count=("next_session_return", "size"),
        )
        .reset_index()
    )
    summary["low_sample"] = summary["sample_count"] < LOW_SAMPLE_THRESHOLD
    return summary.sort_values(["pair", "transition_type", "sample_count"], ascending=[True, True, False]).reset_index(
        drop=True
    )


def summarize_pair_transition_comparison(patterns: pd.DataFrame, transitions: pd.DataFrame) -> pd.DataFrame:
    current_summary = (
        transitions.groupby(["pair", "transition_type"], dropna=False)
        .agg(
            current_continuation_fraction=("continuation_flag", "mean"),
            current_reversal_fraction=("reversal_flag", "mean"),
            avg_current_return=("current_session_return", "mean"),
            avg_current_efficiency=("current_directional_efficiency_ratio", "mean"),
            current_sample_count=("current_session_return", "size"),
        )
        .reset_index()
    )
    next_summary = (
        patterns.groupby(["pair", "transition_type"], dropna=False)
        .agg(
            next_continuation_fraction=("next_continuation_flag", "mean"),
            next_reversal_fraction=("next_reversal_flag", "mean"),
            avg_next_return=("next_session_return", "mean"),
            avg_next_efficiency=("next_directional_efficiency_ratio", "mean"),
            next_sample_count=("next_session_return", "size"),
        )
        .reset_index()
    )
    comparison = current_summary.merge(next_summary, on=["pair", "transition_type"], how="outer")
    comparison["sample_count"] = comparison[["current_sample_count", "next_sample_count"]].min(axis=1)
    comparison["low_sample"] = comparison["sample_count"] < LOW_SAMPLE_THRESHOLD
    return comparison.sort_values(["transition_type", "pair"]).reset_index(drop=True)
