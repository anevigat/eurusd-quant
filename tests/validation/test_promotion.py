from __future__ import annotations

import pandas as pd

from eurusd_quant.validation.promotion import PromotionThresholds, evaluate_promotion


def _thresholds() -> PromotionThresholds:
    return PromotionThresholds(
        min_total_trades=10,
        min_trades_per_year=5,
        min_oos_profit_factor=1.1,
        min_oos_expectancy=0.0,
        max_oos_drawdown=5.0,
        max_single_year_pnl_share=0.6,
        min_stress_profit_factor=1.0,
        min_stress_expectancy=0.0,
    )


def _yearly_metrics() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"year": 2022, "total_trades": 8, "net_pnl": 1.2, "expectancy": 0.15, "profit_factor": 1.3, "max_drawdown": 0.5},
            {"year": 2023, "total_trades": 8, "net_pnl": 0.8, "expectancy": 0.10, "profit_factor": 1.2, "max_drawdown": 0.4},
        ]
    )


def _stress_results(*, stressed_expectancy: float = 0.05) -> dict:
    return {
        "baseline": {"metrics": {"expectancy": 0.12, "profit_factor": 1.25, "net_pnl": 2.0, "max_drawdown": 0.6}},
        "stressed": {"metrics": {"expectancy": stressed_expectancy, "profit_factor": 1.05, "net_pnl": 1.0, "max_drawdown": 0.8}},
        "harsh": {"metrics": {"expectancy": 0.01, "profit_factor": 1.01, "net_pnl": 0.4, "max_drawdown": 1.0}},
    }


def test_evaluate_promotion_rejects_when_core_gate_fails() -> None:
    report = evaluate_promotion(
        aggregate_metrics={"total_trades": 12, "expectancy": 0.1, "profit_factor": 1.2, "max_drawdown": 0.8},
        yearly_metrics=pd.DataFrame(
            [
                {"year": 2022, "total_trades": 10, "net_pnl": 5.0},
                {"year": 2023, "total_trades": 2, "net_pnl": 0.1},
            ]
        ),
        stress_results=_stress_results(stressed_expectancy=-0.01),
        thresholds=_thresholds(),
    )

    assert report["decision"] == "reject"
    assert report["promotion_status"] == "rejected"


def test_evaluate_promotion_returns_continue_when_core_gates_pass_but_extra_evidence_missing() -> None:
    report = evaluate_promotion(
        aggregate_metrics={"total_trades": 16, "expectancy": 0.12, "profit_factor": 1.25, "max_drawdown": 0.7},
        yearly_metrics=_yearly_metrics(),
        stress_results=_stress_results(),
        thresholds=_thresholds(),
    )

    assert report["decision"] == "continue"
    assert report["promotion_status"] == "walk_forward_validated"


def test_evaluate_promotion_returns_paper_trade_candidate_when_all_requirements_pass() -> None:
    report = evaluate_promotion(
        aggregate_metrics={"total_trades": 16, "expectancy": 0.12, "profit_factor": 1.25, "max_drawdown": 0.7},
        yearly_metrics=_yearly_metrics(),
        stress_results=_stress_results(),
        thresholds=_thresholds(),
        parameter_neighborhood={"evaluated_neighbors": 5, "passing_neighbors": 4, "pass_rate": 0.8},
        metadata={"cross_pair_validated": True},
    )

    assert report["decision"] == "paper_trade_candidate"
    assert report["promotion_status"] == "paper_trade_candidate"
