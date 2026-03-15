from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


STRUCTURAL_LOOKBACK_WINDOWS = (24, 48, 96)
FORWARD_RETURN_HORIZONS = (1, 2, 4, 8)


def compute_structural_levels(
    bars: pd.DataFrame,
    *,
    lookback_windows: Iterable[int] = STRUCTURAL_LOOKBACK_WINDOWS,
) -> pd.DataFrame:
    required = {"timestamp", "mid_high", "mid_low", "mid_close"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"bars are missing required columns: {sorted(missing)}")

    frame = bars.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").reset_index(drop=True)

    for window in lookback_windows:
        if window <= 0:
            raise ValueError("lookback windows must be positive")

        prior_high = frame["mid_high"].shift(1).rolling(window, min_periods=window).max()
        prior_low = frame["mid_low"].shift(1).rolling(window, min_periods=window).min()

        frame[f"rolling_high_{window}"] = prior_high
        frame[f"rolling_low_{window}"] = prior_low
        frame[f"break_above_high_{window}"] = frame["mid_high"] > prior_high
        frame[f"break_below_low_{window}"] = frame["mid_low"] < prior_low
        frame[f"sweep_high_{window}"] = frame[f"break_above_high_{window}"] & (frame["mid_close"] < prior_high)
        frame[f"sweep_low_{window}"] = frame[f"break_below_low_{window}"] & (frame["mid_close"] > prior_low)
        frame[f"breakout_high_{window}"] = frame[f"break_above_high_{window}"] & ~frame[f"sweep_high_{window}"]
        frame[f"breakout_low_{window}"] = frame[f"break_below_low_{window}"] & ~frame[f"sweep_low_{window}"]
    return frame


def add_forward_returns(
    bars: pd.DataFrame,
    *,
    horizons: Iterable[int] = FORWARD_RETURN_HORIZONS,
) -> pd.DataFrame:
    frame = bars.copy()
    horizons = tuple(int(h) for h in horizons)
    if not horizons:
        raise ValueError("horizons must not be empty")
    if any(h <= 0 for h in horizons):
        raise ValueError("horizons must be positive")

    for horizon in horizons:
        future_close = frame["mid_close"].shift(-horizon)
        frame[f"forward_return_{horizon}"] = (future_close - frame["mid_close"]) / frame["mid_close"]
        frame[f"forward_abs_return_{horizon}"] = frame[f"forward_return_{horizon}"].abs()
    return frame


def build_extreme_event_inventory(
    bars: pd.DataFrame,
    *,
    pair: str,
    lookback_windows: Iterable[int] = STRUCTURAL_LOOKBACK_WINDOWS,
    horizons: Iterable[int] = FORWARD_RETURN_HORIZONS,
) -> pd.DataFrame:
    required = {
        "timestamp",
        "session",
        "fx_session_date",
        "volatility_regime",
        "mid_open",
        "mid_high",
        "mid_low",
        "mid_close",
    }
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"bars are missing required event columns: {sorted(missing)}")

    frame = compute_structural_levels(bars, lookback_windows=lookback_windows)
    frame = add_forward_returns(frame, horizons=horizons)

    events: list[dict[str, object]] = []
    for window in lookback_windows:
        event_specs = [
            ("breakout_high", "high", f"breakout_high_{window}", f"rolling_high_{window}", 1.0),
            ("breakout_low", "low", f"breakout_low_{window}", f"rolling_low_{window}", -1.0),
            ("sweep_high", "high", f"sweep_high_{window}", f"rolling_high_{window}", 1.0),
            ("sweep_low", "low", f"sweep_low_{window}", f"rolling_low_{window}", -1.0),
        ]
        for event_type, side, flag_col, level_col, direction in event_specs:
            subset = frame.loc[frame[flag_col].fillna(False)].copy()
            if subset.empty:
                continue
            for _, row in subset.iterrows():
                record = {
                    "pair": pair,
                    "timestamp": row["timestamp"],
                    "fx_session_date": row["fx_session_date"],
                    "session": row["session"],
                    "volatility_regime": row["volatility_regime"],
                    "lookback_window": int(window),
                    "event_type": event_type,
                    "event_class": "sweep" if event_type.startswith("sweep") else "breakout",
                    "event_side": side,
                    "event_direction": float(direction),
                    "reference_level": float(row[level_col]) if pd.notna(row[level_col]) else np.nan,
                    "open_price": float(row["mid_open"]),
                    "high_price": float(row["mid_high"]),
                    "low_price": float(row["mid_low"]),
                    "close_price": float(row["mid_close"]),
                }
                for horizon in horizons:
                    forward_return = row[f"forward_return_{horizon}"]
                    record[f"forward_return_{horizon}"] = float(forward_return) if pd.notna(forward_return) else np.nan
                    record[f"forward_abs_return_{horizon}"] = (
                        float(row[f"forward_abs_return_{horizon}"])
                        if pd.notna(row[f"forward_abs_return_{horizon}"])
                        else np.nan
                    )
                    if pd.notna(forward_return):
                        aligned = float(direction * forward_return)
                        record[f"continuation_flag_{horizon}"] = float(aligned > 0)
                        record[f"reversal_flag_{horizon}"] = float(aligned < 0)
                    else:
                        record[f"continuation_flag_{horizon}"] = np.nan
                        record[f"reversal_flag_{horizon}"] = np.nan
                events.append(record)

    if not events:
        return pd.DataFrame(
            columns=[
                "pair",
                "timestamp",
                "fx_session_date",
                "session",
                "volatility_regime",
                "lookback_window",
                "event_type",
                "event_class",
                "event_side",
                "event_direction",
                "reference_level",
                "open_price",
                "high_price",
                "low_price",
                "close_price",
            ]
        )

    event_frame = pd.DataFrame(events).sort_values(["pair", "timestamp", "lookback_window", "event_type"]).reset_index(
        drop=True
    )
    return event_frame


def summarize_post_extreme_forward_returns(
    events: pd.DataFrame,
    *,
    horizons: Iterable[int] = FORWARD_RETURN_HORIZONS,
) -> pd.DataFrame:
    horizons = tuple(int(h) for h in horizons)
    rows: list[dict[str, object]] = []
    for keys, group in events.groupby(["pair", "event_type", "lookback_window"], dropna=False):
        pair, event_type, lookback_window = keys
        for horizon in horizons:
            valid = group[[f"forward_return_{horizon}", f"forward_abs_return_{horizon}"]].dropna()
            rows.append(
                {
                    "pair": pair,
                    "event_type": event_type,
                    "lookback_window": int(lookback_window),
                    "horizon_bars": horizon,
                    "mean_return": float(valid[f"forward_return_{horizon}"].mean()) if not valid.empty else np.nan,
                    "median_return": float(valid[f"forward_return_{horizon}"].median()) if not valid.empty else np.nan,
                    "mean_abs_return": float(valid[f"forward_abs_return_{horizon}"].mean()) if not valid.empty else np.nan,
                    "positive_fraction": float((valid[f"forward_return_{horizon}"] > 0).mean()) if not valid.empty else np.nan,
                    "sample_count": int(len(valid)),
                }
            )
    return pd.DataFrame(rows).sort_values(["pair", "event_type", "lookback_window", "horizon_bars"]).reset_index(
        drop=True
    )


def summarize_sweep_vs_breakout(
    events: pd.DataFrame,
    *,
    horizons: Iterable[int] = FORWARD_RETURN_HORIZONS,
) -> pd.DataFrame:
    horizons = tuple(int(h) for h in horizons)
    rows: list[dict[str, object]] = []
    for keys, group in events.groupby(["pair", "lookback_window", "event_class", "event_side"], dropna=False):
        pair, lookback_window, event_class, event_side = keys
        for horizon in horizons:
            valid = group[
                [
                    f"forward_return_{horizon}",
                    f"forward_abs_return_{horizon}",
                    f"continuation_flag_{horizon}",
                    f"reversal_flag_{horizon}",
                ]
            ].dropna()
            rows.append(
                {
                    "pair": pair,
                    "lookback_window": int(lookback_window),
                    "event_class": event_class,
                    "event_side": event_side,
                    "horizon_bars": horizon,
                    "mean_forward_return": float(valid[f"forward_return_{horizon}"].mean()) if not valid.empty else np.nan,
                    "mean_abs_forward_return": float(valid[f"forward_abs_return_{horizon}"].mean()) if not valid.empty else np.nan,
                    "continuation_probability": float(valid[f"continuation_flag_{horizon}"].mean()) if not valid.empty else np.nan,
                    "reversal_probability": float(valid[f"reversal_flag_{horizon}"].mean()) if not valid.empty else np.nan,
                    "sample_count": int(len(valid)),
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["pair", "lookback_window", "event_class", "event_side", "horizon_bars"]
    ).reset_index(drop=True)


def summarize_context_behavior(
    events: pd.DataFrame,
    *,
    bars: pd.DataFrame,
    context_col: str,
    horizons: Iterable[int] = FORWARD_RETURN_HORIZONS,
) -> pd.DataFrame:
    if context_col not in bars.columns:
        raise ValueError(f"bars are missing context column {context_col!r}")

    horizons = tuple(int(h) for h in horizons)
    sweep_events = events.loc[events["event_class"] == "sweep"].copy()
    bar_counts = (
        bars.groupby(["pair", context_col], dropna=False)
        .size()
        .rename("bars_observed")
        .reset_index()
        .rename(columns={context_col: "context_value"})
    )

    rows: list[dict[str, object]] = []
    for keys, group in sweep_events.groupby(["pair", "lookback_window", "event_type", context_col], dropna=False):
        pair, lookback_window, event_type, context_value = keys
        bars_observed = bar_counts.loc[
            (bar_counts["pair"] == pair) & (bar_counts["context_value"] == context_value), "bars_observed"
        ]
        bars_seen = int(bars_observed.iloc[0]) if not bars_observed.empty else 0
        for horizon in horizons:
            valid = group[
                [
                    f"forward_return_{horizon}",
                    f"reversal_flag_{horizon}",
                ]
            ].dropna()
            sample_count = int(len(valid))
            rows.append(
                {
                    "pair": pair,
                    "lookback_window": int(lookback_window),
                    "event_type": event_type,
                    "context_type": context_col,
                    "context_value": context_value,
                    "horizon_bars": horizon,
                    "event_frequency_per_1000_bars": (sample_count / bars_seen * 1000.0) if bars_seen > 0 else np.nan,
                    "mean_forward_return": float(valid[f"forward_return_{horizon}"].mean()) if not valid.empty else np.nan,
                    "reversal_probability": float(valid[f"reversal_flag_{horizon}"].mean()) if not valid.empty else np.nan,
                    "sample_count": sample_count,
                    "bars_observed": bars_seen,
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["pair", "lookback_window", "event_type", "context_value", "horizon_bars"]
    ).reset_index(drop=True)
