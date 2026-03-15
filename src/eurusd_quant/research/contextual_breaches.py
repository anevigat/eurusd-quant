from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from eurusd_quant.analytics.session_structure import (
    FX_SESSION_ROLLOVER_HOUR_UTC,
    build_session_records,
    ensure_session_columns,
    assign_regimes,
)
from eurusd_quant.analytics.volatility_regimes import assign_time_aware_volatility_regimes
from eurusd_quant.research.structural_extremes import (
    FORWARD_RETURN_HORIZONS,
    STRUCTURAL_LOOKBACK_WINDOWS,
    add_forward_returns,
    compute_structural_levels,
)


CONTEXT_BOUNDARY_BARS = 4
LOW_SAMPLE_THRESHOLD = 30


def _true_range(frame: pd.DataFrame) -> pd.Series:
    prev_close = frame["mid_close"].shift(1)
    intrabar = frame["mid_high"] - frame["mid_low"]
    high_gap = (frame["mid_high"] - prev_close).abs()
    low_gap = (frame["mid_low"] - prev_close).abs()
    return pd.Series(
        np.maximum.reduce(
            [
                intrabar.to_numpy(),
                high_gap.fillna(intrabar).to_numpy(),
                low_gap.fillna(intrabar).to_numpy(),
            ]
        ),
        index=frame.index,
    )


def _pip_multiplier(pair: str) -> float:
    return 100.0 if pair.endswith("JPY") else 10000.0


def assign_session_subcontext(
    bar_index_within_session: pd.Series,
    session_bar_count: pd.Series,
) -> pd.Series:
    if len(bar_index_within_session) != len(session_bar_count):
        raise ValueError("bar_index_within_session and session_bar_count must have the same length")

    position = (bar_index_within_session + 1) / session_bar_count.clip(lower=1)
    return pd.Series(
        np.where(
            position <= 1 / 3,
            "early_session",
            np.where(position <= 2 / 3, "mid_session", "late_session"),
        ),
        index=bar_index_within_session.index,
    )


def assign_transition_context(
    session: pd.Series,
    bar_index_within_session: pd.Series,
    *,
    boundary_bars: int = CONTEXT_BOUNDARY_BARS,
) -> pd.Series:
    if boundary_bars <= 0:
        raise ValueError("boundary_bars must be positive")

    return pd.Series(
        np.where(
            session == "asia",
            "inside_asia",
            np.where(
                (session == "london") & (bar_index_within_session < boundary_bars),
                "asia_to_london_boundary",
                np.where(
                    session == "london",
                    "inside_london",
                    np.where(
                        (session == "new_york") & (bar_index_within_session < boundary_bars),
                        "london_to_new_york_boundary",
                        "inside_new_york",
                    ),
                ),
            ),
        ),
        index=session.index,
    )


def bucket_magnitude(
    values: pd.Series,
    *,
    labels: tuple[str, str, str] = ("small", "medium", "large"),
) -> pd.Series:
    valid = values.dropna()
    if valid.empty:
        return pd.Series("unknown", index=values.index, dtype="object")
    if valid.nunique() == 1:
        result = pd.Series(labels[1], index=values.index, dtype="object")
        result[values.isna()] = "unknown"
        return result

    ranks = valid.rank(method="first")
    buckets = pd.qcut(ranks, q=3, labels=list(labels))
    result = pd.Series(index=values.index, dtype="object")
    result.loc[valid.index] = buckets.astype(str)
    result = result.fillna("unknown")
    return result


def build_bar_context(
    bars: pd.DataFrame,
    *,
    pair: str,
    lookback_sessions: int = 120,
    min_history: int = 30,
    atr_period: int = 14,
    boundary_bars: int = CONTEXT_BOUNDARY_BARS,
) -> pd.DataFrame:
    required = {"timestamp", "mid_open", "mid_high", "mid_low", "mid_close"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"bars are missing required columns: {sorted(missing)}")

    frame = ensure_session_columns(bars, rollover_hour_utc=FX_SESSION_ROLLOVER_HOUR_UTC)
    frame = frame.rename(columns={"session_label": "session"})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["fx_session_date"] = pd.to_datetime(frame["fx_session_date"])
    frame["pair"] = pair
    frame["session_bar_count"] = frame.groupby(["fx_session_date", "session"])["timestamp"].transform("size")
    frame["session_subcontext"] = assign_session_subcontext(
        frame["bar_index_within_session"],
        frame["session_bar_count"],
    )
    frame["transition_context"] = assign_transition_context(
        frame["session"],
        frame["bar_index_within_session"],
        boundary_bars=boundary_bars,
    )

    frame["true_range"] = _true_range(frame)
    frame["atr"] = frame["true_range"].rolling(atr_period, min_periods=1).mean()

    session_records = build_session_records(bars, pair=pair)
    range_records = assign_regimes(session_records)[["pair", "fx_session_date", "session", "range_regime"]]
    vol_records = assign_time_aware_volatility_regimes(
        session_records,
        metric_col="realized_vol",
        lookback_sessions=lookback_sessions,
        min_history=min_history,
    )[["pair", "fx_session_date", "session", "volatility_regime"]]

    context_records = range_records.merge(vol_records, on=["pair", "fx_session_date", "session"], how="inner")
    frame = frame.merge(context_records, on=["pair", "fx_session_date", "session"], how="left")
    frame["range_regime"] = frame["range_regime"].fillna("unknown")
    frame["volatility_regime"] = frame["volatility_regime"].astype("object").fillna("unknown")
    return frame


def add_contextual_breach_features(
    bars: pd.DataFrame,
    *,
    pair: str,
    lookback_windows: Iterable[int] = STRUCTURAL_LOOKBACK_WINDOWS,
    horizons: Iterable[int] = FORWARD_RETURN_HORIZONS,
) -> pd.DataFrame:
    frame = compute_structural_levels(bars, lookback_windows=lookback_windows)
    frame = add_forward_returns(frame, horizons=horizons)
    horizons = tuple(int(h) for h in horizons)
    pip_multiplier = _pip_multiplier(pair)

    for window in lookback_windows:
        high_distance = frame["mid_high"] - frame[f"rolling_high_{window}"]
        low_distance = frame[f"rolling_low_{window}"] - frame["mid_low"]
        frame[f"breach_distance_price_high_{window}"] = high_distance
        frame[f"breach_distance_price_low_{window}"] = low_distance
        frame[f"breach_distance_pips_high_{window}"] = high_distance * pip_multiplier
        frame[f"breach_distance_pips_low_{window}"] = low_distance * pip_multiplier
        frame[f"breach_distance_atr_high_{window}"] = high_distance / frame["atr"].replace(0.0, np.nan)
        frame[f"breach_distance_atr_low_{window}"] = low_distance / frame["atr"].replace(0.0, np.nan)

        for horizon in horizons:
            future_high = pd.concat(
                [frame["mid_high"].shift(-step) for step in range(1, horizon + 1)],
                axis=1,
            ).max(axis=1)
            future_low = pd.concat(
                [frame["mid_low"].shift(-step) for step in range(1, horizon + 1)],
                axis=1,
            ).min(axis=1)
            frame[f"future_high_{horizon}"] = future_high
            frame[f"future_low_{horizon}"] = future_low

    return frame


def build_contextual_breach_inventory(
    bars: pd.DataFrame,
    *,
    pair: str,
    lookback_windows: Iterable[int] = STRUCTURAL_LOOKBACK_WINDOWS,
    horizons: Iterable[int] = FORWARD_RETURN_HORIZONS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {
        "timestamp",
        "fx_session_date",
        "session",
        "bar_index_within_session",
        "session_subcontext",
        "transition_context",
        "volatility_regime",
        "range_regime",
        "atr",
        "mid_close",
    }
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"bars are missing contextual columns: {sorted(missing)}")

    frame = add_contextual_breach_features(bars, pair=pair, lookback_windows=lookback_windows, horizons=horizons)
    horizons = tuple(int(h) for h in horizons)

    inventory_rows: list[dict[str, object]] = []
    outcome_rows: list[dict[str, object]] = []
    event_id = 1

    for window in lookback_windows:
        event_specs = [
            ("breakout_high", "upside", 1.0, f"breakout_high_{window}", "high"),
            ("breakout_low", "downside", -1.0, f"breakout_low_{window}", "low"),
            ("sweep_high", "upside", 1.0, f"sweep_high_{window}", "high"),
            ("sweep_low", "downside", -1.0, f"sweep_low_{window}", "low"),
        ]
        for event_type, direction_label, direction, flag_col, side in event_specs:
            subset = frame.loc[frame[flag_col].fillna(False)].copy()
            for _, row in subset.iterrows():
                if side == "high":
                    breach_price = row[f"breach_distance_price_high_{window}"]
                    breach_pips = row[f"breach_distance_pips_high_{window}"]
                    breach_atr = row[f"breach_distance_atr_high_{window}"]
                else:
                    breach_price = row[f"breach_distance_price_low_{window}"]
                    breach_pips = row[f"breach_distance_pips_low_{window}"]
                    breach_atr = row[f"breach_distance_atr_low_{window}"]

                inventory_rows.append(
                    {
                        "event_id": event_id,
                        "pair": pair,
                        "timestamp": row["timestamp"],
                        "fx_session_date": row["fx_session_date"],
                        "session": row["session"],
                        "bar_index_within_session": int(row["bar_index_within_session"]),
                        "session_subcontext": row["session_subcontext"],
                        "transition_context": row["transition_context"],
                        "volatility_regime": row["volatility_regime"],
                        "range_regime": row["range_regime"],
                        "lookback_window": int(window),
                        "event_type": event_type,
                        "event_class": "sweep" if event_type.startswith("sweep") else "breakout",
                        "direction": direction_label,
                        "event_direction": float(direction),
                        "breach_magnitude_price": float(breach_price) if pd.notna(breach_price) else np.nan,
                        "breach_magnitude_pips": float(breach_pips) if pd.notna(breach_pips) else np.nan,
                        "breach_magnitude_atr": float(breach_atr) if pd.notna(breach_atr) else np.nan,
                    }
                )

                outcome_record: dict[str, object] = {"event_id": event_id}
                close_price = float(row["mid_close"])
                for horizon in horizons:
                    forward_return = row[f"forward_return_{horizon}"]
                    aligned = (direction * forward_return) if pd.notna(forward_return) else np.nan
                    future_high = row[f"future_high_{horizon}"]
                    future_low = row[f"future_low_{horizon}"]
                    if pd.notna(future_high) and pd.notna(future_low):
                        if direction > 0:
                            mfe = max((future_high - close_price) / close_price, 0.0)
                            mae = max((close_price - future_low) / close_price, 0.0)
                        else:
                            mfe = max((close_price - future_low) / close_price, 0.0)
                            mae = max((future_high - close_price) / close_price, 0.0)
                    else:
                        mfe = np.nan
                        mae = np.nan

                    outcome_record[f"forward_return_{horizon}"] = float(forward_return) if pd.notna(forward_return) else np.nan
                    outcome_record[f"aligned_forward_return_{horizon}"] = float(aligned) if pd.notna(aligned) else np.nan
                    outcome_record[f"forward_abs_return_{horizon}"] = (
                        float(row[f"forward_abs_return_{horizon}"])
                        if pd.notna(row[f"forward_abs_return_{horizon}"])
                        else np.nan
                    )
                    outcome_record[f"positive_flag_{horizon}"] = (
                        float(forward_return > 0) if pd.notna(forward_return) else np.nan
                    )
                    outcome_record[f"continuation_flag_{horizon}"] = float(aligned > 0) if pd.notna(aligned) else np.nan
                    outcome_record[f"reversal_flag_{horizon}"] = float(aligned < 0) if pd.notna(aligned) else np.nan
                    outcome_record[f"mfe_{horizon}"] = float(mfe) if pd.notna(mfe) else np.nan
                    outcome_record[f"mae_{horizon}"] = float(mae) if pd.notna(mae) else np.nan
                outcome_rows.append(outcome_record)
                event_id += 1

    inventory = pd.DataFrame(inventory_rows)
    outcomes = pd.DataFrame(outcome_rows)
    if inventory.empty:
        return inventory, outcomes

    inventory["magnitude_bucket"] = (
        inventory.groupby(["pair", "event_type", "lookback_window"], dropna=False)["breach_magnitude_atr"]
        .transform(bucket_magnitude)
        .astype("object")
    )
    inventory = inventory.sort_values(["pair", "timestamp", "lookback_window", "event_type"]).reset_index(drop=True)
    outcomes = outcomes.sort_values("event_id").reset_index(drop=True)
    return inventory, outcomes


def build_long_outcomes(
    inventory: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    horizons: Iterable[int] = FORWARD_RETURN_HORIZONS,
) -> pd.DataFrame:
    horizons = tuple(int(h) for h in horizons)
    merged = inventory.merge(outcomes, on="event_id", how="inner")
    rows: list[dict[str, object]] = []
    base_cols = [
        "event_id",
        "pair",
        "timestamp",
        "session",
        "session_subcontext",
        "transition_context",
        "volatility_regime",
        "range_regime",
        "lookback_window",
        "event_type",
        "event_class",
        "direction",
        "magnitude_bucket",
        "breach_magnitude_price",
        "breach_magnitude_pips",
        "breach_magnitude_atr",
    ]
    for _, row in merged.iterrows():
        base = {column: row[column] for column in base_cols}
        for horizon in horizons:
            rows.append(
                {
                    **base,
                    "horizon_bars": horizon,
                    "forward_return": row[f"forward_return_{horizon}"],
                    "aligned_forward_return": row[f"aligned_forward_return_{horizon}"],
                    "forward_abs_return": row[f"forward_abs_return_{horizon}"],
                    "positive_flag": row[f"positive_flag_{horizon}"],
                    "continuation_flag": row[f"continuation_flag_{horizon}"],
                    "reversal_flag": row[f"reversal_flag_{horizon}"],
                    "mfe": row[f"mfe_{horizon}"],
                    "mae": row[f"mae_{horizon}"],
                }
            )
    return pd.DataFrame(rows)


def summarize_contextual_outcomes(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    summary = (
        frame.groupby(group_cols, dropna=False)
        .agg(
            mean_forward_return=("forward_return", "mean"),
            median_forward_return=("forward_return", "median"),
            mean_aligned_forward_return=("aligned_forward_return", "mean"),
            mean_abs_forward_return=("forward_abs_return", "mean"),
            positive_fraction=("positive_flag", "mean"),
            continuation_fraction=("continuation_flag", "mean"),
            reversal_fraction=("reversal_flag", "mean"),
            mean_mfe=("mfe", "mean"),
            mean_mae=("mae", "mean"),
            forward_return_std=("forward_return", "std"),
            sample_count=("forward_return", "size"),
        )
        .reset_index()
    )
    summary["forward_return_se"] = summary["forward_return_std"] / np.sqrt(summary["sample_count"].clip(lower=1))
    summary["low_sample"] = summary["sample_count"] < LOW_SAMPLE_THRESHOLD
    return summary.sort_values(group_cols).reset_index(drop=True)
