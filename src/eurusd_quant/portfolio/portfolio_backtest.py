from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from eurusd_quant.portfolio.allocator import AllocationConfig, compute_target_weights
from eurusd_quant.portfolio.correlation import (
    compute_daily_pnl_correlation,
    compute_diversification_benefit_summary,
    compute_drawdown_contribution,
)
from eurusd_quant.portfolio.exposure import ExposureConfig, apply_exposure_caps
from eurusd_quant.portfolio.io import StrategyStream, build_active_positions_frame, build_daily_pnl_matrix


@dataclass(frozen=True)
class PortfolioBacktestResult:
    metrics: dict[str, Any]
    equity_curve: pd.DataFrame
    weights: pd.DataFrame
    contribution_by_strategy: pd.DataFrame
    contribution_by_pair: pd.DataFrame
    scaled_trades: pd.DataFrame
    correlation_matrix: pd.DataFrame
    drawdown_contribution: pd.DataFrame


def _rebalance_dates(index: pd.DatetimeIndex, frequency: str) -> list[pd.Timestamp]:
    if len(index) == 0:
        return []
    if frequency == "sample_wide":
        return [index[0]]
    if frequency != "monthly":
        raise ValueError(f"Unsupported rebalance_frequency: {frequency}")

    result: list[pd.Timestamp] = []
    last_marker: tuple[int, int] | None = None
    for date in index:
        marker = (date.year, date.month)
        if marker != last_marker:
            result.append(date)
            last_marker = marker
    return result


def _compute_metrics(portfolio_daily_pnl: pd.Series, scaled_trades: pd.DataFrame, active_weight_count: pd.Series) -> dict[str, Any]:
    equity = portfolio_daily_pnl.cumsum()
    drawdown = equity - equity.cummax()
    annualized_pnl = float(portfolio_daily_pnl.mean() * 252) if not portfolio_daily_pnl.empty else 0.0
    volatility = float(portfolio_daily_pnl.std(ddof=0) * (252**0.5)) if not portfolio_daily_pnl.empty else 0.0
    positives = float(scaled_trades.loc[scaled_trades["weighted_net_pnl"] > 0, "weighted_net_pnl"].sum()) if not scaled_trades.empty else 0.0
    negatives = float(-scaled_trades.loc[scaled_trades["weighted_net_pnl"] < 0, "weighted_net_pnl"].sum()) if not scaled_trades.empty else 0.0
    return {
        "net_pnl": float(portfolio_daily_pnl.sum()),
        "profit_factor": positives / negatives if negatives > 0 else 0.0,
        "expectancy": float(scaled_trades["weighted_net_pnl"].mean()) if not scaled_trades.empty else 0.0,
        "annualized_pnl": annualized_pnl,
        "max_drawdown": float(abs(drawdown.min())) if not drawdown.empty else 0.0,
        "volatility": volatility,
        "return_to_drawdown": float(portfolio_daily_pnl.sum()) / float(abs(drawdown.min())) if not drawdown.empty and drawdown.min() < 0 else 0.0,
        "active_strategies_mean": float(active_weight_count.mean()) if not active_weight_count.empty else 0.0,
        "active_strategies_max": int(active_weight_count.max()) if not active_weight_count.empty else 0,
    }


def run_portfolio_backtest(
    streams: list[StrategyStream],
    allocation_config: AllocationConfig,
    exposure_config: ExposureConfig,
) -> PortfolioBacktestResult:
    daily_pnl = build_daily_pnl_matrix(streams)
    active_positions = build_active_positions_frame(streams)
    if daily_pnl.empty:
        empty = pd.DataFrame()
        return PortfolioBacktestResult(
            metrics={},
            equity_curve=empty,
            weights=empty,
            contribution_by_strategy=empty,
            contribution_by_pair=empty,
            scaled_trades=empty,
            correlation_matrix=empty,
            drawdown_contribution=empty,
        )

    rebalance_dates = set(_rebalance_dates(daily_pnl.index, allocation_config.rebalance_frequency))
    current_target = pd.Series(1.0 / len(daily_pnl.columns), index=daily_pnl.columns, dtype=float)

    weight_rows: list[dict[str, Any]] = []
    portfolio_rows: list[dict[str, Any]] = []
    effective_weight_history: dict[pd.Timestamp, pd.Series] = {}

    for date in daily_pnl.index:
        if date in rebalance_dates:
            history = daily_pnl.loc[daily_pnl.index < date]
            current_target = compute_target_weights(history, allocation_config)
            if current_target.empty:
                current_target = pd.Series(1.0 / len(daily_pnl.columns), index=daily_pnl.columns, dtype=float)
        active_today = active_positions.loc[active_positions["date"] == date]
        effective = apply_exposure_caps(current_target.reindex(daily_pnl.columns).fillna(0.0), active_today, exposure_config)
        effective_weight_history[date] = effective
        day_member_pnl = daily_pnl.loc[date]
        day_portfolio_pnl = float((day_member_pnl * effective).sum())
        portfolio_rows.append(
            {
                "date": date,
                "daily_pnl": day_portfolio_pnl,
                "active_strategies": int((effective > 0).sum()),
            }
        )
        for member_name in daily_pnl.columns:
            weight_rows.append(
                {
                    "date": date,
                    "member_name": member_name,
                    "target_weight": float(current_target.get(member_name, 0.0)),
                    "effective_weight": float(effective.get(member_name, 0.0)),
                    "active": bool(effective.get(member_name, 0.0) > 0),
                }
            )

    weights = pd.DataFrame(weight_rows)
    portfolio_daily = pd.Series(
        [row["daily_pnl"] for row in portfolio_rows],
        index=pd.DatetimeIndex([row["date"] for row in portfolio_rows], tz="UTC"),
        name="daily_pnl",
    )
    equity_curve = pd.DataFrame(
        {
            "date": portfolio_daily.index,
            "daily_pnl": portfolio_daily.values,
            "equity": portfolio_daily.cumsum().values,
        }
    )
    equity_curve["drawdown"] = equity_curve["equity"] - equity_curve["equity"].cummax()

    trades_frames: list[pd.DataFrame] = []
    member_pair_lookup = {stream.name: stream.config.pair.upper() for stream in streams}
    for stream in streams:
        trades = stream.trades.copy()
        if trades.empty:
            continue
        trades["member_name"] = stream.name
        trades["pair"] = stream.config.pair.upper()
        trades["trade_date"] = trades["exit_time"].dt.normalize()
        trades["weight"] = trades["trade_date"].map(lambda date: float(effective_weight_history.get(date, pd.Series()).get(stream.name, 0.0)))
        trades["weighted_net_pnl"] = trades["net_pnl"] * trades["weight"]
        trades_frames.append(trades)
    scaled_trades = pd.concat(trades_frames, ignore_index=True) if trades_frames else pd.DataFrame()

    contribution_by_strategy = (
        scaled_trades.groupby("member_name", sort=True)["weighted_net_pnl"].agg(["sum", "count"]).reset_index()
        if not scaled_trades.empty
        else pd.DataFrame(columns=["member_name", "sum", "count"])
    )
    if not contribution_by_strategy.empty:
        contribution_by_strategy = contribution_by_strategy.rename(columns={"sum": "net_pnl", "count": "trade_count"})
        avg_weights = weights.groupby("member_name", sort=True)["effective_weight"].mean().reset_index(name="average_weight")
        contribution_by_strategy = contribution_by_strategy.merge(avg_weights, on="member_name", how="left")

    contribution_by_pair = (
        scaled_trades.groupby("pair", sort=True)["weighted_net_pnl"].sum().reset_index(name="net_pnl")
        if not scaled_trades.empty
        else pd.DataFrame(columns=["pair", "net_pnl"])
    )
    if not contribution_by_pair.empty:
        pair_weight_rows = (
            weights.assign(pair=weights["member_name"].map(member_pair_lookup))
            .groupby(["date", "pair"], sort=True)["effective_weight"]
            .sum()
            .reset_index()
        )
        pair_avg = pair_weight_rows.groupby("pair", sort=True)["effective_weight"].mean().reset_index(name="average_weight")
        contribution_by_pair = contribution_by_pair.merge(pair_avg, on="pair", how="left")

    active_weight_count = weights.groupby("date", sort=True)["effective_weight"].apply(lambda s: int((s > 0).sum()))
    average_weights = weights.groupby("member_name", sort=True)["effective_weight"].mean()
    diversification = compute_diversification_benefit_summary(daily_pnl, average_weights)
    metrics = _compute_metrics(portfolio_daily, scaled_trades, active_weight_count)
    metrics.update(diversification)
    correlation_matrix = compute_daily_pnl_correlation(daily_pnl)
    drawdown_contribution = compute_drawdown_contribution(daily_pnl, portfolio_daily)

    return PortfolioBacktestResult(
        metrics=metrics,
        equity_curve=equity_curve,
        weights=weights,
        contribution_by_strategy=contribution_by_strategy,
        contribution_by_pair=contribution_by_pair,
        scaled_trades=scaled_trades,
        correlation_matrix=correlation_matrix,
        drawdown_contribution=drawdown_contribution,
    )
