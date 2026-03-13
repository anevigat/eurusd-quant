from __future__ import annotations

import pandas as pd
import pytest

from eurusd_quant.validation.cost_stress import (
    CostStressScenario,
    apply_cost_stress,
    apply_spread_multiplier,
    run_cost_stress_validation,
)


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2024-01-01 00:00:00", tz="UTC")],
            "bid_open": [1.1000],
            "ask_open": [1.1002],
            "bid_high": [1.1005],
            "ask_high": [1.1007],
            "bid_low": [1.0995],
            "ask_low": [1.0997],
            "bid_close": [1.1001],
            "ask_close": [1.1003],
            "spread_open": [0.0002],
            "spread_high": [0.0002],
            "spread_low": [0.0002],
            "spread_close": [0.0002],
        }
    )


def _fake_runner(
    bars: pd.DataFrame,
    strategy_name: str,
    strategy_config: dict,
    execution_config: dict,
) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()

    entry_time = pd.Timestamp(bars["timestamp"].iloc[0])
    spread_cost = float(bars["spread_open"].iloc[0])
    fee = float(execution_config["fee_per_trade"])
    slippage = float(execution_config["market_slippage_pips"]) * 0.01
    net_pnl = 1.0 - spread_cost - fee - slippage
    return pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "side": "long",
                "signal_time": entry_time,
                "entry_time": entry_time,
                "exit_time": entry_time + pd.Timedelta(minutes=15),
                "entry_price": 1.1002,
                "exit_price": 1.1003,
                "stop_loss": 1.0997,
                "take_profit": 1.1007,
                "exit_reason": "time_exit",
                "bars_held": 1,
                "gross_pnl": net_pnl + fee,
                "fee": fee,
                "net_pnl": net_pnl,
                "pnl_pips": net_pnl / 0.0001,
                "slippage_cost": slippage,
                "spread_cost": spread_cost,
            }
        ]
    )


def test_apply_spread_multiplier_preserves_midpoint_and_scales_spread() -> None:
    bars = _bars()
    adjusted = apply_spread_multiplier(bars, 1.5)

    original_mid = (bars.loc[0, "bid_open"] + bars.loc[0, "ask_open"]) / 2.0
    adjusted_mid = (adjusted.loc[0, "bid_open"] + adjusted.loc[0, "ask_open"]) / 2.0

    assert adjusted.loc[0, "spread_open"] == pytest.approx(0.0003)
    assert adjusted_mid == pytest.approx(original_mid)


def test_apply_cost_stress_supports_adders_and_overrides() -> None:
    stressed = apply_cost_stress(
        {"market_slippage_pips": 0.1, "stop_slippage_pips": 0.2, "fee_per_trade": 0.05},
        CostStressScenario(
            name="custom",
            slippage_multiplier=1.5,
            slippage_adder_pips=0.2,
            commission_override=0.25,
        ),
    )

    assert stressed["market_slippage_pips"] == pytest.approx(0.35)
    assert stressed["stop_slippage_pips"] == pytest.approx(0.5)
    assert stressed["fee_per_trade"] == 0.25


def test_run_cost_stress_validation_returns_metrics_per_scenario() -> None:
    execution_config = {
        "market_slippage_pips": 0.1,
        "stop_slippage_pips": 0.2,
        "fee_per_trade": 0.0,
    }
    results = run_cost_stress_validation(
        _bars(),
        "session_breakout",
        {},
        execution_config,
        scenarios=[
            CostStressScenario(name="baseline"),
            CostStressScenario(name="wider_spread", spread_multiplier=2.0, slippage_adder_pips=0.1),
        ],
        runner=_fake_runner,
    )

    assert set(results) == {"baseline", "wider_spread"}
    assert results["baseline"]["metrics"]["total_trades"] == 1
    assert results["wider_spread"]["metrics"]["net_pnl"] < results["baseline"]["metrics"]["net_pnl"]
