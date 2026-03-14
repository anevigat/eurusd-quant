from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

from eurusd_quant.portfolio.io import StrategyStream, build_active_positions_frame, build_daily_pnl_matrix


def compute_daily_pnl_correlation(daily_pnl: pd.DataFrame) -> pd.DataFrame:
    if daily_pnl.empty:
        return pd.DataFrame()
    return daily_pnl.corr()


def compute_rolling_correlations(daily_pnl: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    if daily_pnl.empty or len(daily_pnl.columns) < 2:
        return pd.DataFrame(columns=["date", "left", "right", "correlation"])

    rows: list[dict[str, Any]] = []
    for left, right in combinations(daily_pnl.columns, 2):
        rolling = daily_pnl[left].rolling(window).corr(daily_pnl[right]).dropna()
        for date, value in rolling.items():
            rows.append({"date": date, "left": left, "right": right, "correlation": float(value)})
    return pd.DataFrame(rows)


def compute_trade_overlap_summary(streams: list[StrategyStream]) -> pd.DataFrame:
    active = build_active_positions_frame(streams)
    if active.empty:
        return pd.DataFrame(columns=["left", "right", "overlap_days", "overlap_ratio", "same_pair"])

    day_sets = {
        name: set(group["date"])
        for name, group in active.groupby("member_name", sort=True)
    }
    pair_lookup = {
        stream.name: stream.config.pair.upper()
        for stream in streams
    }
    rows: list[dict[str, Any]] = []
    for left, right in combinations(sorted(day_sets), 2):
        overlap = len(day_sets[left].intersection(day_sets[right]))
        denominator = min(len(day_sets[left]), len(day_sets[right])) or 1
        rows.append(
            {
                "left": left,
                "right": right,
                "overlap_days": overlap,
                "overlap_ratio": float(overlap) / float(denominator),
                "same_pair": pair_lookup.get(left) == pair_lookup.get(right),
            }
        )
    return pd.DataFrame(rows)


def compute_drawdown_contribution(daily_pnl: pd.DataFrame, portfolio_daily_pnl: pd.Series) -> pd.DataFrame:
    if daily_pnl.empty or portfolio_daily_pnl.empty:
        return pd.DataFrame(columns=["member_name", "pnl_during_max_drawdown", "share_of_drawdown"])

    equity = portfolio_daily_pnl.cumsum()
    drawdown = equity - equity.cummax()
    trough = drawdown.idxmin()
    peak = equity.loc[:trough].idxmax()
    window = daily_pnl.loc[(daily_pnl.index >= peak) & (daily_pnl.index <= trough)]
    contributions = window.sum()
    denominator = float(abs(contributions[contributions < 0].sum())) or 1.0
    result = pd.DataFrame(
        {
            "member_name": contributions.index,
            "pnl_during_max_drawdown": contributions.values,
        }
    )
    result["share_of_drawdown"] = result["pnl_during_max_drawdown"].abs() / denominator
    return result.sort_values("pnl_during_max_drawdown")


def compute_diversification_benefit_summary(daily_pnl: pd.DataFrame, average_weights: pd.Series) -> dict[str, float]:
    if daily_pnl.empty:
        return {
            "average_pairwise_correlation": 0.0,
            "max_pairwise_correlation": 0.0,
            "weighted_standalone_volatility": 0.0,
            "portfolio_volatility": 0.0,
            "diversification_ratio": 0.0,
        }

    corr = daily_pnl.corr()
    off_diag = corr.where(~pd.DataFrame(np.eye(len(corr), dtype=bool), index=corr.index, columns=corr.columns)).stack()
    standalone_vol = daily_pnl.std(ddof=0)
    weighted_standalone = float((average_weights.reindex(standalone_vol.index).fillna(0.0) * standalone_vol).sum())
    portfolio_pnl = daily_pnl.mul(average_weights.reindex(daily_pnl.columns).fillna(0.0), axis=1).sum(axis=1)
    portfolio_vol = float(portfolio_pnl.std(ddof=0))
    return {
        "average_pairwise_correlation": float(off_diag.mean()) if not off_diag.empty else 0.0,
        "max_pairwise_correlation": float(off_diag.max()) if not off_diag.empty else 0.0,
        "weighted_standalone_volatility": weighted_standalone,
        "portfolio_volatility": portfolio_vol,
        "diversification_ratio": weighted_standalone / portfolio_vol if portfolio_vol > 0 else 0.0,
    }


def build_correlation_bundle(streams: list[StrategyStream], rolling_window: int = 20) -> dict[str, pd.DataFrame | dict[str, float]]:
    daily_pnl = build_daily_pnl_matrix(streams)
    average_weights = pd.Series(1.0 / len(streams), index=[stream.name for stream in streams]) if streams else pd.Series(dtype=float)
    return {
        "daily_pnl": daily_pnl,
        "correlation_matrix": compute_daily_pnl_correlation(daily_pnl),
        "rolling_correlation": compute_rolling_correlations(daily_pnl, window=rolling_window),
        "overlap_summary": compute_trade_overlap_summary(streams),
        "diversification_summary": compute_diversification_benefit_summary(daily_pnl, average_weights),
    }
