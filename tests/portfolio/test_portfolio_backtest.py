from __future__ import annotations

import pandas as pd

from eurusd_quant.portfolio.allocator import AllocationConfig
from eurusd_quant.portfolio.exposure import ExposureConfig
from eurusd_quant.portfolio.io import PortfolioMemberConfig, StrategyStream
from eurusd_quant.portfolio.portfolio_backtest import run_portfolio_backtest


def make_stream(name: str, pair: str, daily_values: list[float], side: str = "long") -> StrategyStream:
    dates = pd.date_range("2024-01-01", periods=len(daily_values), freq="D", tz="UTC")
    daily = pd.Series(daily_values, index=dates, name="net_pnl")
    trades = pd.DataFrame(
        {
            "symbol": [pair] * len(daily_values),
            "side": [side] * len(daily_values),
            "signal_time": dates,
            "entry_time": dates,
            "exit_time": dates,
            "net_pnl": daily_values,
        }
    )
    active = pd.DataFrame(
        {
            "date": dates,
            "member_name": [name] * len(daily_values),
            "strategy_name": [name] * len(daily_values),
            "pair": [pair] * len(daily_values),
            "side": [side] * len(daily_values),
            "usd_direction": ["usd_short" if pair.endswith("USD") and side == "long" else "usd_long"] * len(daily_values),
        }
    )
    cfg = PortfolioMemberConfig(name=name, strategy=name, pair=pair, timeframe="15m", artifact_path=f"{name}.parquet")
    return StrategyStream(config=cfg, trades=trades, daily_pnl=daily, active_positions=active)


def test_combined_pnl_equals_weighted_sum_without_constraints() -> None:
    streams = [
        make_stream("a", "EURUSD", [1.0, 2.0]),
        make_stream("b", "GBPUSD", [3.0, 1.0]),
    ]
    result = run_portfolio_backtest(
        streams,
        AllocationConfig(weighting_method="equal_weight", rebalance_frequency="sample_wide"),
        ExposureConfig(),
    )
    expected = pd.Series([2.0, 1.5], index=pd.date_range("2024-01-01", periods=2, freq="D", tz="UTC"))
    pd.testing.assert_series_equal(result.equity_curve["daily_pnl"], expected.reset_index(drop=True), check_names=False)


def test_constraints_change_allocation_predictably() -> None:
    streams = [
        make_stream("a", "EURUSD", [1.0, 1.0]),
        make_stream("b", "EURUSD", [1.0, 1.0]),
    ]
    result = run_portfolio_backtest(
        streams,
        AllocationConfig(weighting_method="equal_weight", rebalance_frequency="sample_wide"),
        ExposureConfig(max_active_strategies_per_pair=1),
    )
    first_day = result.weights[result.weights["date"] == pd.Timestamp("2024-01-01", tz="UTC")]
    assert first_day["effective_weight"].sum() == 0.5
    assert int((first_day["effective_weight"] > 0).sum()) == 1


def test_contribution_tables_sum_consistently() -> None:
    streams = [
        make_stream("a", "EURUSD", [1.0, 0.0]),
        make_stream("b", "GBPUSD", [0.0, 2.0]),
    ]
    result = run_portfolio_backtest(
        streams,
        AllocationConfig(weighting_method="equal_weight", rebalance_frequency="sample_wide"),
        ExposureConfig(),
    )
    total_strategy = float(result.contribution_by_strategy["net_pnl"].sum())
    total_pair = float(result.contribution_by_pair["net_pnl"].sum())
    assert round(total_strategy, 10) == round(total_pair, 10)
    assert round(total_strategy, 10) == round(result.metrics["net_pnl"], 10)


def test_metrics_are_deterministic_on_toy_streams() -> None:
    streams = [
        make_stream("a", "EURUSD", [1.0, -1.0, 1.0]),
        make_stream("b", "GBPUSD", [0.5, 0.5, 0.5]),
    ]
    result = run_portfolio_backtest(
        streams,
        AllocationConfig(weighting_method="equal_weight", rebalance_frequency="sample_wide"),
        ExposureConfig(),
    )
    assert "net_pnl" in result.metrics
    assert "max_drawdown" in result.metrics
    assert result.metrics["active_strategies_max"] == 2
