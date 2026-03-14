from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from eurusd_quant.analytics.metrics import compute_metrics
from eurusd_quant.data.sessions import parse_hhmm
from eurusd_quant.validation.metrics import compute_dominant_year_pnl_share


DEFAULT_FORWARD_HORIZONS: tuple[int, ...] = (1, 2, 4, 8)


def _true_range(frame: pd.DataFrame) -> pd.Series:
    prev_close = frame["mid_close"].shift(1)
    intrabar = frame["mid_high"] - frame["mid_low"]
    high_gap = (frame["mid_high"] - prev_close).abs()
    low_gap = (frame["mid_low"] - prev_close).abs()
    return np.maximum.reduce(
        [
            intrabar.to_numpy(),
            high_gap.fillna(intrabar).to_numpy(),
            low_gap.fillna(intrabar).to_numpy(),
        ]
    )


def compute_impulse_events(
    bars: pd.DataFrame,
    *,
    impulse_start_utc: str = "13:00",
    impulse_end_utc: str = "13:30",
    forward_horizons: Iterable[int] = DEFAULT_FORWARD_HORIZONS,
    atr_period: int = 14,
) -> pd.DataFrame:
    horizons = tuple(int(value) for value in forward_horizons)
    if not horizons:
        raise ValueError("forward_horizons must not be empty")
    if atr_period <= 0:
        raise ValueError("atr_period must be positive")

    frame = bars.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    frame["trade_date"] = frame["timestamp"].dt.date
    frame["time_utc"] = frame["timestamp"].dt.time
    frame["atr"] = pd.Series(_true_range(frame), index=frame.index).rolling(
        atr_period, min_periods=1
    ).mean()

    impulse_start = parse_hhmm(impulse_start_utc)
    impulse_end = parse_hhmm(impulse_end_utc)
    impulse_mask = (frame["time_utc"] >= impulse_start) & (frame["time_utc"] < impulse_end)
    impulse_window = frame.loc[impulse_mask].copy()

    base_columns = [
        "trade_date",
        "year",
        "month",
        "impulse_start_time",
        "impulse_end_time",
        "impulse_open",
        "impulse_close",
        "impulse_high",
        "impulse_low",
        "impulse_size",
        "impulse_direction",
        "atr",
        "impulse_atr_ratio",
    ]
    derived_columns: list[str] = []
    for horizon in horizons:
        derived_columns.extend(
            [f"forward_return_{horizon}", f"signed_reversion_return_{horizon}"]
        )
    if impulse_window.empty:
        return pd.DataFrame(columns=[*base_columns, *derived_columns])

    events = (
        impulse_window.groupby("trade_date", as_index=False)
        .agg(
            impulse_start_time=("timestamp", "min"),
            impulse_end_time=("timestamp", "max"),
            impulse_open=("mid_open", "first"),
            impulse_close=("mid_close", "last"),
            impulse_high=("mid_high", "max"),
            impulse_low=("mid_low", "min"),
            atr=("atr", "last"),
        )
        .sort_values("trade_date")
        .reset_index(drop=True)
    )
    events["year"] = pd.to_datetime(events["trade_date"]).dt.year
    events["month"] = pd.to_datetime(events["trade_date"]).dt.strftime("%Y-%m")
    events["impulse_size"] = events["impulse_high"] - events["impulse_low"]
    events["impulse_direction"] = np.where(
        events["impulse_close"] > events["impulse_open"],
        "up",
        np.where(events["impulse_close"] < events["impulse_open"], "down", "flat"),
    )
    events["impulse_atr_ratio"] = np.where(
        events["atr"] > 0.0,
        events["impulse_size"] / events["atr"],
        np.nan,
    )

    index_by_timestamp = pd.Series(frame.index.to_numpy(), index=frame["timestamp"])
    direction_sign = events["impulse_direction"].map({"up": 1.0, "down": -1.0}).fillna(0.0)

    for horizon in horizons:
        forward_returns: list[float | None] = []
        for impulse_end_time in events["impulse_end_time"]:
            idx = index_by_timestamp.get(impulse_end_time)
            if idx is None or int(idx) + horizon >= len(frame):
                forward_returns.append(None)
                continue
            future_close = float(frame.iloc[int(idx) + horizon]["mid_close"])
            impulse_close = float(frame.iloc[int(idx)]["mid_close"])
            forward_returns.append(future_close - impulse_close)
        events[f"forward_return_{horizon}"] = forward_returns
        events[f"signed_reversion_return_{horizon}"] = -direction_sign * events[
            f"forward_return_{horizon}"
        ]

    return events


def assign_event_volatility_regimes(
    events: pd.DataFrame,
    *,
    low_quantile: float = 0.30,
    high_quantile: float = 0.70,
) -> tuple[pd.DataFrame, dict[str, float]]:
    if events.empty:
        empty = events.copy()
        empty["volatility_regime"] = pd.Series(dtype=str)
        return empty, {"low_quantile_threshold": 0.0, "high_quantile_threshold": 0.0}
    if not 0.0 < low_quantile < high_quantile < 1.0:
        raise ValueError("low_quantile and high_quantile must satisfy 0 < low < high < 1")

    frame = events.copy()
    low_threshold = float(frame["atr"].quantile(low_quantile))
    high_threshold = float(frame["atr"].quantile(high_quantile))
    frame["volatility_regime"] = np.where(
        frame["atr"] <= low_threshold,
        "low_vol",
        np.where(frame["atr"] >= high_threshold, "high_vol", "mid_vol"),
    )
    return frame, {
        "low_quantile_threshold": low_threshold,
        "high_quantile_threshold": high_threshold,
    }


def summarize_impulse_distribution(events: pd.DataFrame, *, pip_size: float) -> dict[str, Any]:
    if pip_size <= 0.0:
        raise ValueError("pip_size must be positive")
    if events.empty:
        return {
            "total_impulses": 0,
            "direction_counts": {},
            "impulse_size_pips": {},
        }

    size_pips = events["impulse_size"] / pip_size
    return {
        "total_impulses": int(len(events)),
        "direction_counts": {
            str(key): int(value)
            for key, value in events["impulse_direction"].value_counts().sort_index().items()
        },
        "impulse_size_pips": {
            "min": float(size_pips.min()),
            "median": float(size_pips.median()),
            "mean": float(size_pips.mean()),
            "p75": float(size_pips.quantile(0.75)),
            "p90": float(size_pips.quantile(0.90)),
            "max": float(size_pips.max()),
        },
    }


def summarize_forward_returns(
    events: pd.DataFrame,
    *,
    horizons: Iterable[int] = DEFAULT_FORWARD_HORIZONS,
    pip_size: float,
) -> dict[str, Any]:
    if pip_size <= 0.0:
        raise ValueError("pip_size must be positive")
    summary: dict[str, Any] = {}
    for horizon in horizons:
        forward_col = f"forward_return_{horizon}"
        reversion_col = f"signed_reversion_return_{horizon}"
        if forward_col not in events.columns or reversion_col not in events.columns:
            raise ValueError(f"Events are missing required columns for horizon {horizon}")

        summary[str(horizon)] = {
            "all": _build_return_bucket(events, forward_col, reversion_col, pip_size),
            "up": _build_return_bucket(
                events.loc[events["impulse_direction"] == "up"],
                forward_col,
                reversion_col,
                pip_size,
            ),
            "down": _build_return_bucket(
                events.loc[events["impulse_direction"] == "down"],
                forward_col,
                reversion_col,
                pip_size,
            ),
        }
        if "volatility_regime" in events.columns:
            summary[str(horizon)]["low_vol"] = _build_return_bucket(
                events.loc[events["volatility_regime"] == "low_vol"],
                forward_col,
                reversion_col,
                pip_size,
            )
            summary[str(horizon)]["high_vol"] = _build_return_bucket(
                events.loc[events["volatility_regime"] == "high_vol"],
                forward_col,
                reversion_col,
                pip_size,
            )
    return summary


def _build_return_bucket(
    frame: pd.DataFrame,
    forward_col: str,
    reversion_col: str,
    pip_size: float,
) -> dict[str, Any]:
    valid = frame[[forward_col, reversion_col]].dropna()
    if valid.empty:
        return {
            "count": 0,
            "mean_return_pips": 0.0,
            "mean_reversion_return_pips": 0.0,
        }
    return {
        "count": int(len(valid)),
        "mean_return_pips": float(valid[forward_col].mean() / pip_size),
        "mean_reversion_return_pips": float(valid[reversion_col].mean() / pip_size),
    }


def summarize_trade_density(
    trades: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = trades.copy()
    for column in ("signal_time", "entry_time", "exit_time"):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], utc=True)
    if frame.empty:
        empty = pd.DataFrame()
        return (
            {
                "total_trades": 0,
                "dominant_year_pnl_share": 0.0,
                "zero_trade_month_count": 0,
                "longest_zero_trade_gap_months": 0,
            },
            empty,
            empty,
            empty,
            empty,
        )
    if "signal_time" not in frame.columns:
        raise ValueError("Trades are missing required column 'signal_time'")
    if "net_pnl" not in frame.columns:
        raise ValueError("Trades are missing required column 'net_pnl'")

    frame["year"] = frame["signal_time"].dt.year
    frame["month"] = frame["signal_time"].dt.strftime("%Y-%m")
    frame["signal_window_utc"] = frame["signal_time"].dt.strftime("%H:%M")

    yearly = (
        frame.groupby("year", as_index=False)
        .agg(
            trade_count=("net_pnl", "size"),
            net_pnl=("net_pnl", "sum"),
            expectancy=("net_pnl", "mean"),
            win_rate=("net_pnl", lambda s: float((s > 0).mean()) if len(s) else 0.0),
            profit_factor=("net_pnl", _profit_factor),
        )
        .sort_values("year")
        .reset_index(drop=True)
    )
    monthly = (
        frame.groupby("month", as_index=False)
        .agg(
            trade_count=("net_pnl", "size"),
            net_pnl=("net_pnl", "sum"),
        )
        .sort_values("month")
        .reset_index(drop=True)
    )
    signal_windows = (
        frame.groupby("signal_window_utc", as_index=False)
        .agg(
            trade_count=("net_pnl", "size"),
            net_pnl=("net_pnl", "sum"),
            expectancy=("net_pnl", "mean"),
            profit_factor=("net_pnl", _profit_factor),
        )
        .sort_values("signal_window_utc")
        .reset_index(drop=True)
    )

    zero_trade_months = _build_zero_trade_months(frame["signal_time"])
    summary = {
        "total_trades": int(len(frame)),
        "dominant_year_pnl_share": float(compute_dominant_year_pnl_share(yearly)),
        "zero_trade_month_count": int(len(zero_trade_months)),
        "longest_zero_trade_gap_months": int(zero_trade_months["gap_size_months"].max())
        if not zero_trade_months.empty
        else 0,
        "metrics": compute_metrics(frame),
    }
    return summary, yearly, monthly, signal_windows, zero_trade_months


def _build_zero_trade_months(signal_times: pd.Series) -> pd.DataFrame:
    months = signal_times.dt.strftime("%Y-%m")
    if months.empty:
        return pd.DataFrame(columns=["month", "gap_group", "gap_size_months"])

    period_index = pd.PeriodIndex(months, freq="M")
    full_range = pd.period_range(period_index.min(), period_index.max(), freq="M")
    present = set(months)
    rows: list[dict[str, Any]] = []
    gap_group = 0
    current_gap_size = 0

    for month in full_range.astype(str):
        if month in present:
            current_gap_size = 0
            continue
        if current_gap_size == 0:
            gap_group += 1
        current_gap_size += 1
        rows.append(
            {
                "month": month,
                "gap_group": gap_group,
                "gap_size_months": current_gap_size,
            }
        )

    return pd.DataFrame(rows)


def _profit_factor(pnl: pd.Series) -> float:
    wins = float(pnl[pnl > 0].sum())
    losses_abs = abs(float(pnl[pnl < 0].sum()))
    if losses_abs == 0.0:
        return float(np.inf) if wins > 0.0 else 0.0
    return float(wins / losses_abs)
