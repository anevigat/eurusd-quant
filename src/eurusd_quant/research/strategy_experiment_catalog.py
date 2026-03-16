from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_hypothesis_catalog(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "hypothesis_id",
        "family",
        "priority_tier",
        "source_candidate_ids",
        "pair_scope",
        "session_context",
        "range_regime",
        "volatility_regime",
        "breach_type",
        "breach_direction",
        "magnitude_bucket",
        "expected_direction",
        "evaluation_horizon",
        "status",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"hypothesis catalog is missing required columns: {sorted(missing)}")
    return frame


def build_experiment_catalog(hypotheses: pd.DataFrame) -> pd.DataFrame:
    hypothesis_by_id = hypotheses.set_index("hypothesis_id")
    required_ids = {"H1A", "H1B", "H2", "H3"}
    missing_ids = required_ids.difference(hypothesis_by_id.index)
    if missing_ids:
        raise ValueError(f"hypothesis catalog is missing expected hypothesis ids: {sorted(missing_ids)}")

    rows = [
        {
            "experiment_id": "EXP_H1A_01",
            "hypothesis_id": "H1A",
            "priority_tier": "Tier 1",
            "pair_scope": "EURUSD|GBPUSD",
            "session_context": "London",
            "range_regime": "strongly_expanded",
            "volatility_regime": "all",
            "breach_type": "breakout_low|sweep_low",
            "breach_direction": "downside",
            "magnitude_bucket": "small|medium",
            "entry_style": "breach_bar_close",
            "exit_style": "fixed_h4_horizon",
            "evaluation_horizon": "h4",
            "validation_sequence": "logic_test>smoke_backtest>focused_sweep>walk_forward>cost_stress>robustness>portfolio_check",
            "status": "planned_primary",
            "notes": "Primary pooled European-pair London downside continuation experiment with the structural condition locked and only execution timing left open later.",
        },
        {
            "experiment_id": "EXP_H1A_02",
            "hypothesis_id": "H1A",
            "priority_tier": "Tier 1",
            "pair_scope": "EURUSD|GBPUSD",
            "session_context": "London",
            "range_regime": "strongly_expanded",
            "volatility_regime": "all",
            "breach_type": "breakout_low|sweep_low",
            "breach_direction": "downside",
            "magnitude_bucket": "small|medium",
            "entry_style": "one_bar_confirmation",
            "exit_style": "fixed_h4_horizon",
            "evaluation_horizon": "h4",
            "validation_sequence": "logic_test>smoke_backtest>focused_sweep>walk_forward>cost_stress>robustness>portfolio_check",
            "status": "planned_primary",
            "notes": "Single bounded H1A entry variant to test whether confirmation improves robustness without widening the family.",
        },
        {
            "experiment_id": "EXP_H1B_01",
            "hypothesis_id": "H1B",
            "priority_tier": "Tier 1",
            "pair_scope": "EURUSD|GBPUSD",
            "session_context": "early New York",
            "range_regime": "strongly_expanded",
            "volatility_regime": "all",
            "breach_type": "sweep_low",
            "breach_direction": "downside",
            "magnitude_bucket": "medium",
            "entry_style": "breach_bar_close",
            "exit_style": "fixed_h4_horizon",
            "evaluation_horizon": "h4",
            "validation_sequence": "logic_test>smoke_backtest>focused_sweep>walk_forward>cost_stress>robustness>portfolio_check",
            "status": "planned_primary",
            "notes": "Primary early-New-York downside continuation experiment; should be compared directly against H1A under identical reporting rules.",
        },
        {
            "experiment_id": "EXP_H2_01",
            "hypothesis_id": "H2",
            "priority_tier": "Tier 2",
            "pair_scope": "USDJPY",
            "session_context": "New York",
            "range_regime": "strongly_expanded",
            "volatility_regime": "all",
            "breach_type": "breakout_high",
            "breach_direction": "upside",
            "magnitude_bucket": "small",
            "entry_style": "breach_bar_close",
            "exit_style": "fixed_h4_horizon",
            "evaluation_horizon": "h4",
            "validation_sequence": "logic_test>smoke_backtest>focused_sweep>walk_forward>cost_stress>robustness>portfolio_check",
            "status": "planned_secondary",
            "notes": "Pair-specific USDJPY branch; no pooled inference and stricter sensitivity requirements apply.",
        },
        {
            "experiment_id": "EXP_H3_01",
            "hypothesis_id": "H3",
            "priority_tier": "Tier 3",
            "pair_scope": "ALL",
            "session_context": "early New York",
            "range_regime": "strongly_expanded",
            "volatility_regime": "all",
            "breach_type": "sweep_high",
            "breach_direction": "upside",
            "magnitude_bucket": "small",
            "entry_style": "breach_bar_close",
            "exit_style": "fixed_h4_horizon",
            "evaluation_horizon": "h4",
            "validation_sequence": "logic_test>smoke_backtest>focused_sweep>walk_forward",
            "status": "deferred",
            "notes": "Tier 3 side case is explicitly deferred until H1/H2 are resolved; no immediate implementation budget.",
        },
    ]
    return pd.DataFrame(rows)


def build_validation_ladder() -> pd.DataFrame:
    rows = [
        {
            "stage_order": 1,
            "stage_name": "logic_test",
            "purpose": "Verify deterministic event detection, direction handling, and session/regime gating before backtesting.",
            "required_outputs": "unit_test_results",
            "required_metrics": "pass_fail,test_case_count",
            "fast_rejection_rule": "reject if event logic or sign normalization fails deterministic tests",
        },
        {
            "stage_order": 2,
            "stage_name": "smoke_backtest",
            "purpose": "Check that the strategy runs end-to-end on the intended pair scope with the locked research condition.",
            "required_outputs": "metrics.json,equity_curve.csv,trades.parquet",
            "required_metrics": "net_pnl,trade_count,profit_factor,max_drawdown",
            "fast_rejection_rule": "reject if full-sample net pnl is clearly negative or trade count is too low to continue",
        },
        {
            "stage_order": 3,
            "stage_name": "focused_sweep",
            "purpose": "Test only the small allowed execution variants such as breach-close vs one-bar confirmation.",
            "required_outputs": "top_configs.csv,sweep_metrics.csv",
            "required_metrics": "net_pnl,profit_factor,expectancy,trade_count",
            "fast_rejection_rule": "reject if the edge disappears under one nearby execution variation",
        },
        {
            "stage_order": 4,
            "stage_name": "walk_forward",
            "purpose": "Evaluate OOS stability under the shared Phase 1 walk-forward protocol.",
            "required_outputs": "splits.csv,aggregate.json,promotion_report.json",
            "required_metrics": "oos_profit_factor,oos_expectancy,oos_trade_count,yearly_breakdown",
            "fast_rejection_rule": "reject if OOS outcome is negative, unstable, or dominated by one year",
        },
        {
            "stage_order": 5,
            "stage_name": "cost_stress",
            "purpose": "Check that the edge survives realistic friction increases.",
            "required_outputs": "cost_stress_summary.csv",
            "required_metrics": "baseline_pf,stressed_pf,baseline_net_pnl,stressed_net_pnl",
            "fast_rejection_rule": "reject if a small cost increase flips the sign immediately",
        },
        {
            "stage_order": 6,
            "stage_name": "robustness",
            "purpose": "Run cross-pair robustness for pooled hypotheses or stricter pair-specific sensitivity for H2.",
            "required_outputs": "robustness_summary.csv",
            "required_metrics": "pair_breakdown,parameter_neighborhood,stability_flags",
            "fast_rejection_rule": "reject if pair pooling hides contradiction or pair-specific sensitivity is too fragile",
        },
        {
            "stage_order": 7,
            "stage_name": "portfolio_check",
            "purpose": "Only for survivors: test whether the experiment adds something beyond existing sleeves.",
            "required_outputs": "portfolio_comparison.json",
            "required_metrics": "correlation,contribution,max_drawdown_change,return_drawdown_ratio",
            "fast_rejection_rule": "reject if the experiment adds no diversification or worsens portfolio behavior disproportionately",
        },
    ]
    return pd.DataFrame(rows)
