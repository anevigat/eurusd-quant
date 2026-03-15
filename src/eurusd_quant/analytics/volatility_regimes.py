from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


REGIME_ORDER = ("unknown", "low_vol", "medium_vol", "high_vol")


def assign_time_aware_volatility_regimes(
    session_records: pd.DataFrame,
    *,
    metric_col: str = "realized_vol",
    lookback_sessions: int = 120,
    min_history: int = 30,
    low_quantile: float = 1 / 3,
    high_quantile: float = 2 / 3,
) -> pd.DataFrame:
    if metric_col not in session_records.columns:
        raise ValueError(f"session_records are missing {metric_col!r}")
    if lookback_sessions <= 0:
        raise ValueError("lookback_sessions must be positive")
    if min_history <= 0:
        raise ValueError("min_history must be positive")
    if not 0.0 < low_quantile < high_quantile < 1.0:
        raise ValueError("Quantiles must satisfy 0 < low_quantile < high_quantile < 1")

    frame = session_records.copy()
    frame = frame.sort_values(["pair", "session_start"]).reset_index(drop=True)

    regime_labels: list[str] = []
    history_counts: list[int] = []
    low_thresholds: list[float] = []
    high_thresholds: list[float] = []

    for _, pair_group in frame.groupby("pair", sort=False):
        values = pair_group[metric_col].tolist()
        for idx, current in enumerate(values):
            start_idx = max(0, idx - lookback_sessions)
            history = pd.Series(values[start_idx:idx]).dropna()
            history_count = int(len(history))
            history_counts.append(history_count)
            if history_count < min_history or pd.isna(current):
                regime_labels.append("unknown")
                low_thresholds.append(np.nan)
                high_thresholds.append(np.nan)
                continue

            low_threshold = float(history.quantile(low_quantile))
            high_threshold = float(history.quantile(high_quantile))
            low_thresholds.append(low_threshold)
            high_thresholds.append(high_threshold)
            if current <= low_threshold:
                regime_labels.append("low_vol")
            elif current >= high_threshold:
                regime_labels.append("high_vol")
            else:
                regime_labels.append("medium_vol")

    frame["volatility_regime_metric"] = frame[metric_col]
    frame["volatility_regime_history_count"] = history_counts
    frame["volatility_regime_low_threshold"] = low_thresholds
    frame["volatility_regime_high_threshold"] = high_thresholds
    frame["volatility_regime"] = pd.Categorical(regime_labels, categories=list(REGIME_ORDER), ordered=True)
    return frame


def compute_session_step_forward_returns(
    session_records: pd.DataFrame,
    *,
    horizons: Iterable[int] = (1, 2, 4, 8),
) -> pd.DataFrame:
    frame = session_records.copy()
    frame = frame.sort_values(["pair", "session_start"]).reset_index(drop=True)
    horizons = tuple(int(h) for h in horizons)
    if not horizons:
        raise ValueError("horizons must not be empty")
    if any(h <= 0 for h in horizons):
        raise ValueError("horizons must be positive")

    for pair, pair_group in frame.groupby("pair", sort=False):
        idx = pair_group.index
        pair_close = pair_group["close_price"]
        for horizon in horizons:
            future_close = pair_close.shift(-horizon)
            frame.loc[idx, f"forward_return_{horizon}"] = (future_close - pair_close) / pair_close
            frame.loc[idx, f"forward_abs_return_{horizon}"] = frame.loc[idx, f"forward_return_{horizon}"].abs()
            frame.loc[idx, f"forward_positive_{horizon}"] = (frame.loc[idx, f"forward_return_{horizon}"] > 0).astype(float)
    return frame


def summarize_regime_descriptives(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    summary = (
        frame.groupby(group_cols, dropna=False, observed=True)
        .agg(
            sample_count=("session_return", "size"),
            avg_vol_metric=("volatility_regime_metric", "mean"),
            avg_range=("session_range_return", "mean"),
            avg_abs_return=("session_abs_return", "mean"),
            avg_signed_return=("session_return", "mean"),
            avg_efficiency=("directional_efficiency_ratio", "mean"),
            avg_clv=("close_location_value", "mean"),
            avg_session_realized_vol=("realized_vol", "mean"),
            vol_metric_std=("volatility_regime_metric", "std"),
        )
        .reset_index()
    )
    summary["vol_metric_se"] = summary["vol_metric_std"] / np.sqrt(summary["sample_count"].clip(lower=1))
    return summary.sort_values(group_cols).reset_index(drop=True)


def build_regime_runs(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values(["pair", "session_start"]).reset_index(drop=True)
    ordered["prev_pair"] = ordered["pair"].shift(1)
    ordered["prev_regime"] = ordered["volatility_regime"].shift(1)
    ordered["run_start"] = (ordered["pair"] != ordered["prev_pair"]) | (
        ordered["volatility_regime"] != ordered["prev_regime"]
    )
    ordered["run_id"] = ordered["run_start"].cumsum()
    runs = (
        ordered.groupby(["pair", "volatility_regime", "run_id"], observed=True)
        .agg(
            run_start=("session_start", "min"),
            run_end=("session_end", "max"),
            duration_sessions=("session_return", "size"),
        )
        .reset_index()
    )
    return runs


def summarize_regime_persistence(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values(["pair", "session_start"]).reset_index(drop=True)
    ordered["next_pair"] = ordered["pair"].shift(-1)
    ordered["next_regime"] = ordered["volatility_regime"].shift(-1)
    ordered["same_next_pair"] = ordered["pair"] == ordered["next_pair"]
    ordered["stay_same_regime_next"] = (
        ordered["same_next_pair"] & (ordered["volatility_regime"] == ordered["next_regime"])
    ).astype(float)

    runs = build_regime_runs(frame)
    run_summary = (
        runs.groupby(["pair", "volatility_regime"], observed=True)
        .agg(
            run_count=("duration_sessions", "size"),
            avg_duration_sessions=("duration_sessions", "mean"),
            median_duration_sessions=("duration_sessions", "median"),
            p90_duration_sessions=("duration_sessions", lambda s: float(s.quantile(0.90))),
            max_duration_sessions=("duration_sessions", "max"),
        )
        .reset_index()
    )

    stay_summary = (
        ordered.loc[ordered["same_next_pair"]]
        .groupby(["pair", "volatility_regime"], observed=True)
        .agg(
            persistence_probability=("stay_same_regime_next", "mean"),
            transition_sample_count=("stay_same_regime_next", "size"),
        )
        .reset_index()
    )

    merged = run_summary.merge(stay_summary, on=["pair", "volatility_regime"], how="left").sort_values(
        ["pair", "volatility_regime"]
    )
    merged["sample_count"] = merged["transition_sample_count"].fillna(merged["run_count"])
    return merged


def summarize_regime_transition_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values(["pair", "session_start"]).reset_index(drop=True)
    ordered["next_pair"] = ordered["pair"].shift(-1)
    ordered["next_regime"] = ordered["volatility_regime"].shift(-1)
    transitions = ordered.loc[
        (ordered["pair"] == ordered["next_pair"])
        & ordered["volatility_regime"].notna()
        & ordered["next_regime"].notna()
    ].copy()
    transitions = transitions.rename(
        columns={
            "volatility_regime": "from_regime",
            "next_regime": "to_regime",
        }
    )
    matrix = (
        transitions.groupby(["pair", "from_regime", "to_regime"], observed=True)
        .agg(transition_count=("session_return", "size"))
        .reset_index()
    )
    matrix["sample_count"] = matrix.groupby(["pair", "from_regime"], observed=True)["transition_count"].transform("sum")
    matrix["transition_probability"] = matrix["transition_count"] / matrix["sample_count"]

    pooled = (
        transitions.groupby(["from_regime", "to_regime"], observed=True)
        .agg(transition_count=("session_return", "size"))
        .reset_index()
    )
    pooled.insert(0, "pair", "ALL")
    pooled["sample_count"] = pooled.groupby(["pair", "from_regime"], observed=True)["transition_count"].transform("sum")
    pooled["transition_probability"] = pooled["transition_count"] / pooled["sample_count"]

    return pd.concat([matrix, pooled], ignore_index=True).sort_values(
        ["pair", "from_regime", "to_regime"]
    ).reset_index(drop=True)


def summarize_forward_returns_by_regime(
    frame: pd.DataFrame,
    *,
    horizons: Iterable[int] = (1, 2, 4, 8),
) -> pd.DataFrame:
    horizons = tuple(int(h) for h in horizons)
    rows: list[dict[str, object]] = []
    grouping_specs = [
        ("pair_regime", ["pair", "volatility_regime"]),
        ("pair_regime_session", ["pair", "volatility_regime", "session"]),
        ("pooled_regime", ["volatility_regime"]),
    ]
    for scope, group_cols in grouping_specs:
        for keys, group in frame.groupby(group_cols, dropna=False, observed=True):
            key_values = keys if isinstance(keys, tuple) else (keys,)
            base = dict(zip(group_cols, key_values, strict=False))
            if scope == "pooled_regime":
                base["pair"] = "ALL"
                base["session"] = "ALL"
            elif scope == "pair_regime":
                base["session"] = "ALL"
            for horizon in horizons:
                ret_col = f"forward_return_{horizon}"
                abs_col = f"forward_abs_return_{horizon}"
                pos_col = f"forward_positive_{horizon}"
                valid = group[[ret_col, abs_col, pos_col]].dropna()
                rows.append(
                    {
                        "scope": scope,
                        "pair": base["pair"],
                        "volatility_regime": base["volatility_regime"],
                        "session": base["session"],
                        "horizon_sessions": horizon,
                        "mean_forward_return": float(valid[ret_col].mean()) if not valid.empty else np.nan,
                        "median_forward_return": float(valid[ret_col].median()) if not valid.empty else np.nan,
                        "mean_abs_forward_return": float(valid[abs_col].mean()) if not valid.empty else np.nan,
                        "positive_return_fraction": float(valid[pos_col].mean()) if not valid.empty else np.nan,
                        "forward_return_std": float(valid[ret_col].std(ddof=0)) if not valid.empty else np.nan,
                        "sample_count": int(len(valid)),
                    }
                )
    result = pd.DataFrame(rows)
    result["forward_return_se"] = result["forward_return_std"] / np.sqrt(result["sample_count"].clip(lower=1))
    return result.sort_values(["scope", "pair", "volatility_regime", "session", "horizon_sessions"]).reset_index(drop=True)


def summarize_session_behavior_by_regime(frame: pd.DataFrame) -> pd.DataFrame:
    summary = (
        frame.groupby(["pair", "session", "volatility_regime"], dropna=False, observed=True)
        .agg(
            avg_session_return=("session_return", "mean"),
            avg_session_abs_return=("session_abs_return", "mean"),
            continuation_probability=("continuation_flag", "mean"),
            reversal_probability=("reversal_flag", "mean"),
            avg_directional_efficiency_ratio=("directional_efficiency_ratio", "mean"),
            avg_close_location_value=("close_location_value", "mean"),
            sample_count=("session_return", "size"),
        )
        .reset_index()
    )
    return summary.sort_values(["pair", "session", "volatility_regime"]).reset_index(drop=True)


def summarize_session_regime_transitions(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values(["pair", "fx_session_date", "session_start"]).reset_index(drop=True)
    ordered["next_pair"] = ordered["pair"].shift(-1)
    ordered["next_session"] = ordered["session"].shift(-1)
    ordered["next_regime"] = ordered["volatility_regime"].shift(-1)
    ordered["next_return"] = ordered["session_return"].shift(-1)
    ordered["next_abs_return"] = ordered["session_abs_return"].shift(-1)
    ordered["next_continuation"] = ordered["continuation_flag"].shift(-1)

    transitions = ordered.loc[
        (ordered["pair"] == ordered["next_pair"])
        & (
            ((ordered["session"] == "asia") & (ordered["next_session"] == "london"))
            | ((ordered["session"] == "london") & (ordered["next_session"] == "new_york"))
        )
    ].copy()
    transitions["session_transition"] = np.where(
        transitions["session"] == "asia",
        "asia_to_london",
        "london_to_new_york",
    )
    transitions = transitions.rename(columns={"volatility_regime": "prior_volatility_regime"})

    summary = (
        transitions.groupby(
            ["pair", "session_transition", "prior_volatility_regime", "next_regime"],
            dropna=False,
            observed=True,
        )
        .agg(
            transition_frequency=("session_return", "size"),
            avg_next_session_return=("next_return", "mean"),
            avg_next_session_abs_return=("next_abs_return", "mean"),
            next_session_continuation_probability=("next_continuation", "mean"),
        )
        .reset_index()
    )
    summary["sample_count"] = summary.groupby(
        ["pair", "session_transition", "prior_volatility_regime"], observed=True
    )["transition_frequency"].transform("sum")
    summary["transition_probability"] = summary["transition_frequency"] / summary["sample_count"]

    pooled = (
        transitions.groupby(
            ["session_transition", "prior_volatility_regime", "next_regime"],
            dropna=False,
            observed=True,
        )
        .agg(
            transition_frequency=("session_return", "size"),
            avg_next_session_return=("next_return", "mean"),
            avg_next_session_abs_return=("next_abs_return", "mean"),
            next_session_continuation_probability=("next_continuation", "mean"),
        )
        .reset_index()
    )
    pooled.insert(0, "pair", "ALL")
    pooled["sample_count"] = pooled.groupby(
        ["pair", "session_transition", "prior_volatility_regime"], observed=True
    )["transition_frequency"].transform("sum")
    pooled["transition_probability"] = pooled["transition_frequency"] / pooled["sample_count"]

    return pd.concat([summary, pooled], ignore_index=True).sort_values(
        ["pair", "session_transition", "prior_volatility_regime", "next_regime"]
    ).reset_index(drop=True)
