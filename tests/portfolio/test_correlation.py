from __future__ import annotations

from dataclasses import replace

import pandas as pd

from eurusd_quant.portfolio.correlation import (
    compute_daily_pnl_correlation,
    compute_trade_overlap_summary,
)
from eurusd_quant.portfolio.io import PortfolioMemberConfig, StrategyStream


def make_stream(name: str, pair: str, daily_values: list[float], active_dates: list[str]) -> StrategyStream:
    dates = pd.date_range("2024-01-01", periods=len(daily_values), freq="D", tz="UTC")
    daily = pd.Series(daily_values, index=dates, name="net_pnl")
    active = pd.DataFrame(
        {
            "date": pd.to_datetime(active_dates, utc=True),
            "member_name": name,
            "strategy_name": name,
            "pair": pair,
            "side": "long",
            "usd_direction": "usd_short",
        }
    )
    cfg = PortfolioMemberConfig(name=name, strategy=name, pair=pair, timeframe="15m", artifact_path=f"{name}.parquet")
    trades = pd.DataFrame({"exit_time": dates[:1], "entry_time": dates[:1], "side": ["long"], "net_pnl": [daily_values[0]]})
    return StrategyStream(config=cfg, trades=trades, daily_pnl=daily, active_positions=active)


def test_identical_streams_show_high_correlation() -> None:
    daily = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0, 3.0]})
    corr = compute_daily_pnl_correlation(daily)
    assert corr.loc["a", "b"] == 1.0


def test_orthogonal_toy_streams_show_low_correlation() -> None:
    daily = pd.DataFrame({"a": [1.0, -1.0, 1.0, -1.0], "b": [1.0, 1.0, -1.0, -1.0]})
    corr = compute_daily_pnl_correlation(daily)
    assert abs(float(corr.loc["a", "b"])) < 0.1


def test_overlap_counts_are_correct() -> None:
    stream_a = make_stream("a", "EURUSD", [1.0, 0.0], ["2024-01-01", "2024-01-02"])
    stream_b = make_stream("b", "EURUSD", [0.0, 1.0], ["2024-01-02", "2024-01-03"])
    overlap = compute_trade_overlap_summary([stream_a, stream_b])
    assert int(overlap.loc[0, "overlap_days"]) == 1
    assert bool(overlap.loc[0, "same_pair"]) is True
