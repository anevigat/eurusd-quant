from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


FX_SESSION_ROLLOVER_HOUR_UTC = 22
SESSION_ORDER = ("asia", "london", "new_york")
SESSION_WINDOWS_UTC = {
    "asia": ("00:00", "07:00"),
    "london": ("07:00", "13:00"),
    "new_york": ("13:00", "24:00"),
}


def label_session(timestamp: pd.Timestamp) -> str:
    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    hour = ts.hour
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 13:
        return "london"
    return "new_york"


def compute_fx_session_date(
    timestamp: pd.Series | pd.DatetimeIndex,
    *,
    rollover_hour_utc: int = FX_SESSION_ROLLOVER_HOUR_UTC,
) -> pd.Series:
    shifted = pd.to_datetime(timestamp, utc=True) + pd.Timedelta(hours=24 - rollover_hour_utc)
    if isinstance(shifted, pd.Series):
        return shifted.dt.date
    return pd.Series(shifted.date, index=getattr(timestamp, "index", None))


def ensure_session_columns(
    bars: pd.DataFrame,
    *,
    rollover_hour_utc: int = FX_SESSION_ROLLOVER_HOUR_UTC,
) -> pd.DataFrame:
    frame = bars.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    if "session_label" not in frame.columns:
        frame["session_label"] = frame["timestamp"].map(label_session)
    frame["fx_session_date"] = compute_fx_session_date(
        frame["timestamp"],
        rollover_hour_utc=rollover_hour_utc,
    )
    frame["bar_index_within_session"] = frame.groupby(["fx_session_date", "session_label"]).cumcount()
    return frame


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


def _bars_since_last_extreme(extreme_mask: pd.Series) -> pd.Series:
    positions = np.arange(len(extreme_mask))
    last_extreme = np.where(extreme_mask.to_numpy(), positions, np.nan)
    last_extreme = pd.Series(last_extreme, index=extreme_mask.index).ffill()
    distance = positions - last_extreme.to_numpy()
    distance = np.where(np.isnan(last_extreme.to_numpy()), np.nan, distance)
    return pd.Series(distance, index=extreme_mask.index)


def build_session_records(
    bars: pd.DataFrame,
    *,
    pair: str,
    rollover_hour_utc: int = FX_SESSION_ROLLOVER_HOUR_UTC,
    atr_period: int = 14,
    extreme_move_atr_multiple: float = 1.5,
) -> pd.DataFrame:
    if atr_period <= 0:
        raise ValueError("atr_period must be positive")
    if extreme_move_atr_multiple <= 0:
        raise ValueError("extreme_move_atr_multiple must be positive")

    frame = ensure_session_columns(bars, rollover_hour_utc=rollover_hour_utc)
    frame["bar_return"] = frame["mid_close"].pct_change()
    frame["true_range"] = _true_range(frame)
    frame["atr"] = frame["true_range"].rolling(atr_period, min_periods=1).mean()
    frame["bar_body"] = (frame["mid_close"] - frame["mid_open"]).abs()
    frame["extreme_bar"] = frame["bar_body"] >= (extreme_move_atr_multiple * frame["atr"])
    frame["bars_since_extreme"] = _bars_since_last_extreme(frame["extreme_bar"])
    frame["prev_close_in_session"] = frame.groupby(["fx_session_date", "session_label"])["mid_close"].shift(1)
    frame["prev_close_in_session"] = frame["prev_close_in_session"].fillna(frame["mid_open"])
    frame["path_step"] = (frame["mid_close"] - frame["prev_close_in_session"]).abs()

    records: list[dict[str, object]] = []
    for (fx_session_date, session_label), group in frame.groupby(["fx_session_date", "session_label"], sort=True):
        group = group.reset_index(drop=True)
        open_price = float(group.iloc[0]["mid_open"])
        close_price = float(group.iloc[-1]["mid_close"])
        high_price = float(group["mid_high"].max())
        low_price = float(group["mid_low"].min())
        session_move = close_price - open_price
        initial_move = float(group.iloc[0]["mid_close"] - group.iloc[0]["mid_open"])
        session_sign = np.sign(session_move)
        initial_sign = np.sign(initial_move)
        session_range = high_price - low_price
        records.append(
            {
                "pair": pair,
                "session": session_label,
                "fx_session_date": pd.Timestamp(fx_session_date),
                "session_start": group.iloc[0]["timestamp"],
                "session_end": group.iloc[-1]["timestamp"],
                "open_price": open_price,
                "close_price": close_price,
                "high_price": high_price,
                "low_price": low_price,
                "session_return": session_move / open_price if open_price else np.nan,
                "session_abs_return": abs(session_move / open_price) if open_price else np.nan,
                "session_range_return": session_range / open_price if open_price else np.nan,
                "bullish_session": float(session_sign > 0),
                "bearish_session": float(session_sign < 0),
                "continuation_flag": float(initial_sign != 0 and session_sign == initial_sign),
                "reversal_flag": float(initial_sign != 0 and session_sign == -initial_sign),
                "realized_vol": float(group["bar_return"].dropna().std(ddof=0) or 0.0),
                "sample_bars": int(len(group)),
                "initial_bar_return": initial_move / open_price if open_price else np.nan,
                "directional_efficiency_ratio": (
                    abs(session_move) / float(group["path_step"].sum())
                    if float(group["path_step"].sum()) > 0
                    else 0.0
                ),
                "close_location_value": (
                    (close_price - low_price) / session_range if session_range > 0 else 0.5
                ),
                "session_start_bars_since_extreme": float(group.iloc[0]["bars_since_extreme"])
                if pd.notna(group.iloc[0]["bars_since_extreme"])
                else np.nan,
            }
        )

    return pd.DataFrame(records).sort_values(["pair", "fx_session_date", "session"]).reset_index(drop=True)


def _quantile_bucket(series: pd.Series, labels: Iterable[str]) -> pd.Series:
    labels = list(labels)
    valid = series.dropna()
    if valid.empty:
        return pd.Series(pd.Categorical([None] * len(series), categories=labels), index=series.index)
    unique_count = valid.nunique()
    if unique_count == 1:
        filled = pd.Series(labels[len(labels) // 2], index=series.index, dtype="object")
        filled[series.isna()] = None
        return filled
    ranks = valid.rank(method="first")
    buckets = pd.qcut(ranks, q=len(labels), labels=labels)
    result = pd.Series(index=series.index, dtype="object")
    result.loc[valid.index] = buckets.astype(str)
    return result


def assign_regimes(session_records: pd.DataFrame) -> pd.DataFrame:
    frame = session_records.copy()
    frame = frame.sort_values(["pair", "session", "fx_session_date"]).reset_index(drop=True)
    frame["volatility_regime"] = (
        frame.groupby(["pair", "session"], group_keys=False, observed=False)["realized_vol"]
        .apply(lambda s: _quantile_bucket(s, ("low", "medium", "high")))
        .astype("object")
    )

    frame["trailing_range_baseline"] = (
        frame.groupby(["pair", "session"], observed=False)["session_range_return"]
        .transform(lambda s: s.shift(1).rolling(20, min_periods=5).median())
    )
    frame["range_ratio_vs_baseline"] = frame["session_range_return"] / frame["trailing_range_baseline"]
    frame["range_regime"] = np.where(
        frame["range_ratio_vs_baseline"].isna(),
        "unknown",
        np.where(
            frame["range_ratio_vs_baseline"] < 0.8,
            "compressed",
            np.where(frame["range_ratio_vs_baseline"] > 1.2, "expanded", "normal"),
        ),
    )

    bars_since = frame["session_start_bars_since_extreme"]
    frame["extreme_regime"] = np.where(
        bars_since.isna(),
        "stale",
        np.where(
            bars_since <= 8,
            "recent_extreme",
            np.where(bars_since <= 32, "intermediate", "stale"),
        ),
    )
    return frame


def summarize_session_behavior(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    summary = (
        frame.groupby(group_cols, dropna=False, observed=False)
        .agg(
            avg_return=("session_return", "mean"),
            median_return=("session_return", "median"),
            avg_abs_return=("session_abs_return", "mean"),
            avg_range=("session_range_return", "mean"),
            continuation_prob=("continuation_flag", "mean"),
            reversal_prob=("reversal_flag", "mean"),
            bullish_frac=("bullish_session", "mean"),
            bearish_frac=("bearish_session", "mean"),
            realized_vol=("realized_vol", "mean"),
            avg_directional_efficiency_ratio=("directional_efficiency_ratio", "mean"),
            avg_close_location_value=("close_location_value", "mean"),
            sample_count=("session_return", "size"),
        )
        .reset_index()
    )
    return summary.sort_values(group_cols).reset_index(drop=True)


def build_distribution_summary(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    metrics = [
        "session_return",
        "session_abs_return",
        "session_range_return",
        "realized_vol",
        "directional_efficiency_ratio",
        "close_location_value",
    ]
    for keys, group in frame.groupby(group_cols, dropna=False, observed=False):
        key_values = keys if isinstance(keys, tuple) else (keys,)
        base = dict(zip(group_cols, key_values, strict=False))
        base["sample_count"] = int(len(group))
        for metric in metrics:
            values = group[metric].dropna()
            row = base.copy()
            row["metric"] = metric
            row["mean"] = float(values.mean()) if not values.empty else np.nan
            row["p10"] = float(values.quantile(0.10)) if not values.empty else np.nan
            row["p25"] = float(values.quantile(0.25)) if not values.empty else np.nan
            row["p50"] = float(values.quantile(0.50)) if not values.empty else np.nan
            row["p75"] = float(values.quantile(0.75)) if not values.empty else np.nan
            row["p90"] = float(values.quantile(0.90)) if not values.empty else np.nan
            rows.append(row)
    return pd.DataFrame(rows).sort_values(group_cols + ["metric"]).reset_index(drop=True)


def build_transition_records(session_records: pd.DataFrame) -> pd.DataFrame:
    frame = session_records.copy()
    frame["session_order"] = frame["session"].map({name: idx for idx, name in enumerate(SESSION_ORDER)})
    frame = frame.sort_values(["pair", "fx_session_date", "session_order"]).reset_index(drop=True)

    rows: list[dict[str, object]] = []
    transition_pairs = {"asia_to_london": ("asia", "london"), "london_to_new_york": ("london", "new_york")}
    for (pair, fx_session_date), group in frame.groupby(["pair", "fx_session_date"], sort=True):
        by_session = {row["session"]: row for _, row in group.iterrows()}
        for transition_name, (prior_session, next_session) in transition_pairs.items():
            if prior_session not in by_session or next_session not in by_session:
                continue
            prior = by_session[prior_session]
            nxt = by_session[next_session]
            prior_sign = np.sign(prior["session_return"])
            next_sign = np.sign(nxt["session_return"])
            rows.append(
                {
                    "pair": pair,
                    "fx_session_date": fx_session_date,
                    "transition": transition_name,
                    "prior_session": prior_session,
                    "next_session": next_session,
                    "prior_session_return": prior["session_return"],
                    "next_session_return": nxt["session_return"],
                    "next_session_range": nxt["session_range_return"],
                    "prior_session_sign": "positive" if prior_sign > 0 else "negative" if prior_sign < 0 else "flat",
                    "continue_flag": float(prior_sign != 0 and next_sign == prior_sign),
                    "reverse_flag": float(prior_sign != 0 and next_sign == -prior_sign),
                    "prior_volatility_regime": prior["volatility_regime"],
                }
            )
    return pd.DataFrame(rows)


def summarize_transitions(transitions: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if transitions.empty:
        return pd.DataFrame(columns=[*group_cols, "continuation_prob", "reversal_prob", "avg_next_session_return", "avg_next_session_range", "sample_count"])
    summary = (
        transitions.groupby(group_cols, dropna=False, observed=False)
        .agg(
            continuation_prob=("continue_flag", "mean"),
            reversal_prob=("reverse_flag", "mean"),
            avg_next_session_return=("next_session_return", "mean"),
            avg_next_session_range=("next_session_range", "mean"),
            sample_count=("next_session_return", "size"),
        )
        .reset_index()
    )
    return summary.sort_values(group_cols).reset_index(drop=True)
