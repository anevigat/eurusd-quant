from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

import pandas as pd

from eurusd_quant.backtest import BacktestResult, run_backtest
from eurusd_quant.validation.metrics import build_validation_summary


@dataclass(frozen=True)
class CostStressScenario:
    name: str
    spread_multiplier: float = 1.0
    slippage_multiplier: float = 1.0
    slippage_adder_pips: float = 0.0
    commission_multiplier: float = 1.0
    commission_override: float | None = None


def build_default_cost_stress_scenarios() -> list[CostStressScenario]:
    return [
        CostStressScenario(name="baseline"),
        CostStressScenario(name="stressed", spread_multiplier=1.25, slippage_multiplier=1.25, commission_multiplier=1.25),
        CostStressScenario(name="harsh", spread_multiplier=1.50, slippage_multiplier=1.50, commission_multiplier=1.50),
    ]


def apply_spread_multiplier(bars: pd.DataFrame, spread_multiplier: float) -> pd.DataFrame:
    if spread_multiplier <= 0.0:
        raise ValueError("spread_multiplier must be positive")
    if spread_multiplier == 1.0:
        return bars.copy()

    adjusted = bars.copy()
    for suffix in ("open", "high", "low", "close"):
        bid_col = f"bid_{suffix}"
        ask_col = f"ask_{suffix}"
        spread_col = f"spread_{suffix}"
        mid = (adjusted[bid_col] + adjusted[ask_col]) / 2.0
        spread = (adjusted[ask_col] - adjusted[bid_col]) * spread_multiplier
        adjusted[bid_col] = mid - (spread / 2.0)
        adjusted[ask_col] = mid + (spread / 2.0)
        adjusted[spread_col] = adjusted[ask_col] - adjusted[bid_col]
    return adjusted


def apply_cost_stress(
    execution_config: dict[str, Any],
    scenario: CostStressScenario,
) -> dict[str, Any]:
    stressed = dict(execution_config)
    stressed["market_slippage_pips"] = (
        float(execution_config["market_slippage_pips"]) * scenario.slippage_multiplier
    ) + scenario.slippage_adder_pips
    stressed["stop_slippage_pips"] = (
        float(execution_config["stop_slippage_pips"]) * scenario.slippage_multiplier
    ) + scenario.slippage_adder_pips
    if scenario.commission_override is not None:
        stressed["fee_per_trade"] = float(scenario.commission_override)
    else:
        stressed["fee_per_trade"] = float(execution_config["fee_per_trade"]) * scenario.commission_multiplier
    return stressed


def _extract_trades(result: BacktestResult | pd.DataFrame) -> pd.DataFrame:
    if isinstance(result, BacktestResult):
        return result.trades
    return result


def run_cost_stress_validation(
    bars: pd.DataFrame,
    strategy_name: str,
    strategy_config: dict[str, Any],
    execution_config: dict[str, Any],
    *,
    scenarios: list[CostStressScenario] | None = None,
    runner: Callable[[pd.DataFrame, str, dict[str, Any], dict[str, Any]], BacktestResult | pd.DataFrame] | None = None,
) -> dict[str, dict[str, Any]]:
    scenarios = scenarios or build_default_cost_stress_scenarios()
    runner = runner or run_backtest

    results: dict[str, dict[str, Any]] = {}
    for scenario in scenarios:
        stressed_bars = apply_spread_multiplier(bars, scenario.spread_multiplier)
        stressed_execution = apply_cost_stress(execution_config, scenario)
        trades = _extract_trades(runner(stressed_bars, strategy_name, strategy_config, stressed_execution))
        results[scenario.name] = {
            "scenario": asdict(scenario),
            "metrics": build_validation_summary(trades),
        }
    return results
