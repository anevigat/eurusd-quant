from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import json
from typing import Any, Callable

import pandas as pd

from eurusd_quant.backtest import BacktestResult, run_backtest
from eurusd_quant.validation.cost_stress import (
    CostStressScenario,
    apply_cost_stress,
    apply_spread_multiplier,
    build_default_cost_stress_scenarios,
)
from eurusd_quant.validation.metrics import (
    build_validation_summary,
    compute_daily_equity_curve,
    compute_yearly_metrics,
    normalize_trades,
)
from eurusd_quant.validation.promotion import PromotionThresholds, evaluate_promotion


@dataclass(frozen=True)
class WalkForwardSplit:
    split_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


@dataclass(frozen=True)
class WalkForwardResult:
    config_hash: str
    splits: list[WalkForwardSplit]
    splits_df: pd.DataFrame
    aggregate_metrics: dict[str, Any]
    yearly_metrics: pd.DataFrame
    equity_curve: pd.DataFrame
    promotion_report: dict[str, Any]
    stress_results: dict[str, dict[str, Any]]
    oos_trades: pd.DataFrame


def config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, default=str)
    return sha1(payload.encode("utf-8")).hexdigest()[:12]


def generate_walk_forward_splits(
    bars: pd.DataFrame,
    *,
    train_years: int,
    test_months: int,
    embargo_days: int = 0,
) -> list[WalkForwardSplit]:
    if bars.empty:
        return []
    if train_years <= 0:
        raise ValueError("train_years must be positive")
    if test_months <= 0:
        raise ValueError("test_months must be positive")
    if embargo_days < 0:
        raise ValueError("embargo_days cannot be negative")

    timestamps = pd.to_datetime(bars["timestamp"], utc=True)
    start = timestamps.min().normalize()
    end = timestamps.max()
    embargo = pd.Timedelta(days=embargo_days)

    splits: list[WalkForwardSplit] = []
    split_id = 1
    train_start = start
    while True:
        train_end = train_start + pd.DateOffset(years=train_years)
        test_start = train_end + embargo
        test_end = test_start + pd.DateOffset(months=test_months)
        if test_end > end:
            break
        splits.append(
            WalkForwardSplit(
                split_id=split_id,
                train_start=pd.Timestamp(train_start),
                train_end=pd.Timestamp(train_end),
                test_start=pd.Timestamp(test_start),
                test_end=pd.Timestamp(test_end),
            )
        )
        split_id += 1
        train_start = train_start + pd.DateOffset(months=test_months)
    return splits


def _extract_trades(result: BacktestResult | pd.DataFrame) -> pd.DataFrame:
    if isinstance(result, BacktestResult):
        return result.trades
    return result


def run_walk_forward_validation(
    bars: pd.DataFrame,
    strategy_name: str,
    strategy_config: dict[str, Any],
    execution_config: dict[str, Any],
    *,
    train_years: int,
    test_months: int,
    embargo_days: int = 0,
    thresholds: PromotionThresholds | None = None,
    cost_stress_scenarios: list[CostStressScenario] | None = None,
    parameter_neighborhood: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    runner: Callable[[pd.DataFrame, str, dict[str, Any], dict[str, Any]], BacktestResult | pd.DataFrame] | None = None,
) -> WalkForwardResult:
    thresholds = thresholds or PromotionThresholds()
    metadata = metadata or {}
    runner = runner or run_backtest

    normalized_bars = bars.copy()
    normalized_bars["timestamp"] = pd.to_datetime(normalized_bars["timestamp"], utc=True)
    splits = generate_walk_forward_splits(
        normalized_bars,
        train_years=train_years,
        test_months=test_months,
        embargo_days=embargo_days,
    )
    if not splits:
        raise ValueError("No walk-forward splits were produced for the supplied dataset and window sizes")

    split_rows: list[dict[str, Any]] = []
    oos_trade_parts: list[pd.DataFrame] = []

    for split in splits:
        train_mask = (normalized_bars["timestamp"] >= split.train_start) & (normalized_bars["timestamp"] < split.train_end)
        test_mask = (normalized_bars["timestamp"] >= split.test_start) & (normalized_bars["timestamp"] < split.test_end)

        train_bars = normalized_bars.loc[train_mask].reset_index(drop=True)
        test_bars = normalized_bars.loc[test_mask].reset_index(drop=True)
        train_trades = normalize_trades(_extract_trades(runner(train_bars, strategy_name, strategy_config, execution_config)))
        test_trades = normalize_trades(_extract_trades(runner(test_bars, strategy_name, strategy_config, execution_config)))

        if not test_trades.empty:
            tagged = test_trades.copy()
            tagged["split_id"] = split.split_id
            tagged["test_start"] = split.test_start
            tagged["test_end"] = split.test_end
            oos_trade_parts.append(tagged)

        train_summary = build_validation_summary(train_trades)
        test_summary = build_validation_summary(test_trades)
        split_rows.append(
            {
                "split_id": split.split_id,
                "train_start": split.train_start.isoformat(),
                "train_end": split.train_end.isoformat(),
                "test_start": split.test_start.isoformat(),
                "test_end": split.test_end.isoformat(),
                "train_total_trades": int(train_summary["total_trades"]),
                "train_expectancy": float(train_summary["expectancy"]),
                "train_profit_factor": float(train_summary["profit_factor"]),
                "train_net_pnl": float(train_summary["net_pnl"]),
                "test_total_trades": int(test_summary["total_trades"]),
                "test_expectancy": float(test_summary["expectancy"]),
                "test_profit_factor": float(test_summary["profit_factor"]),
                "test_net_pnl": float(test_summary["net_pnl"]),
                "test_max_drawdown": float(test_summary["max_drawdown"]),
            }
        )

    oos_trades = pd.concat(oos_trade_parts, ignore_index=True) if oos_trade_parts else pd.DataFrame()
    aggregate_metrics = build_validation_summary(oos_trades)
    yearly_metrics = compute_yearly_metrics(oos_trades)
    equity_curve = compute_daily_equity_curve(oos_trades)

    scenario_list = cost_stress_scenarios or build_default_cost_stress_scenarios()
    stress_results: dict[str, dict[str, Any]] = {
        "baseline": {"scenario": {"name": "baseline"}, "metrics": aggregate_metrics}
    }
    non_baseline_scenarios = [scenario for scenario in scenario_list if scenario.name != "baseline"]
    if non_baseline_scenarios:
        scenario_trade_parts: dict[str, list[pd.DataFrame]] = {scenario.name: [] for scenario in non_baseline_scenarios}
        for split in splits:
            test_mask = (normalized_bars["timestamp"] >= split.test_start) & (normalized_bars["timestamp"] < split.test_end)
            test_bars = normalized_bars.loc[test_mask].reset_index(drop=True)
            for scenario in non_baseline_scenarios:
                stressed_bars = apply_spread_multiplier(test_bars, scenario.spread_multiplier)
                stressed_execution = apply_cost_stress(execution_config, scenario)
                trades = normalize_trades(_extract_trades(runner(stressed_bars, strategy_name, strategy_config, stressed_execution)))
                if not trades.empty:
                    scenario_trade_parts[scenario.name].append(trades)
        for scenario in non_baseline_scenarios:
            combined = (
                normalize_trades(pd.concat(scenario_trade_parts[scenario.name], ignore_index=True))
                if scenario_trade_parts[scenario.name]
                else pd.DataFrame()
            )
            stress_results[scenario.name] = {
                "scenario": {
                    "name": scenario.name,
                    "spread_multiplier": scenario.spread_multiplier,
                    "slippage_multiplier": scenario.slippage_multiplier,
                    "slippage_adder_pips": scenario.slippage_adder_pips,
                    "commission_multiplier": scenario.commission_multiplier,
                    "commission_override": scenario.commission_override,
                },
                "metrics": build_validation_summary(combined),
            }

    promotion_report = evaluate_promotion(
        aggregate_metrics,
        yearly_metrics,
        stress_results,
        thresholds=thresholds,
        parameter_neighborhood=parameter_neighborhood,
        metadata=metadata,
    )

    return WalkForwardResult(
        config_hash=config_hash(strategy_config),
        splits=splits,
        splits_df=pd.DataFrame(split_rows),
        aggregate_metrics=aggregate_metrics,
        yearly_metrics=yearly_metrics,
        equity_curve=equity_curve,
        promotion_report=promotion_report,
        stress_results=stress_results,
        oos_trades=oos_trades,
    )
