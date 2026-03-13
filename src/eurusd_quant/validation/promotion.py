from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from eurusd_quant.validation.metrics import compute_dominant_year_pnl_share


@dataclass(frozen=True)
class PromotionThresholds:
    min_total_trades: int = 200
    min_trades_per_year: int = 50
    min_oos_profit_factor: float = 1.10
    min_oos_expectancy: float = 0.0
    max_oos_drawdown: float = 0.02
    max_single_year_pnl_share: float = 0.45
    min_stress_profit_factor: float = 1.0
    min_stress_expectancy: float = 0.0
    required_stress_scenarios: tuple[str, ...] = ("stressed", "harsh")
    min_neighborhood_pass_rate: float = 0.60
    min_neighbor_count: int = 3

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromotionThresholds":
        normalized = dict(data)
        if "required_stress_scenarios" in normalized and isinstance(normalized["required_stress_scenarios"], list):
            normalized["required_stress_scenarios"] = tuple(normalized["required_stress_scenarios"])
        return cls(**normalized)


def _gate(
    name: str,
    passed: bool | None,
    actual: Any,
    threshold: Any,
    description: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "actual": actual,
        "threshold": threshold,
        "description": description,
    }


def _normalize_optional_bool(value: Any, field_name: str) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no", ""}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    raise ValueError(f"{field_name} must be a boolean-compatible value")


def _evaluate_parameter_neighborhood(
    parameter_neighborhood: dict[str, Any] | None,
    thresholds: PromotionThresholds,
) -> dict[str, Any]:
    if parameter_neighborhood is None:
        return _gate(
            name="parameter_neighborhood_stability",
            passed=None,
            actual=None,
            threshold={
                "min_neighbor_count": thresholds.min_neighbor_count,
                "min_pass_rate": thresholds.min_neighborhood_pass_rate,
            },
            description="Parameter neighborhood stability requires adjacent sweep results and was not evaluated.",
        )

    evaluated_neighbors = int(parameter_neighborhood.get("evaluated_neighbors", 0))
    passing_neighbors = int(parameter_neighborhood.get("passing_neighbors", 0))
    pass_rate = float(parameter_neighborhood.get("pass_rate", 0.0))
    passed = evaluated_neighbors >= thresholds.min_neighbor_count and pass_rate >= thresholds.min_neighborhood_pass_rate
    return _gate(
        name="parameter_neighborhood_stability",
        passed=passed,
        actual={
            "evaluated_neighbors": evaluated_neighbors,
            "passing_neighbors": passing_neighbors,
            "pass_rate": pass_rate,
        },
        threshold={
            "min_neighbor_count": thresholds.min_neighbor_count,
            "min_pass_rate": thresholds.min_neighborhood_pass_rate,
        },
        description="Neighboring parameter sets should also survive validation to reduce single-point overfit risk.",
    )


def _evaluate_stress_survival(
    stress_results: dict[str, dict[str, Any]],
    thresholds: PromotionThresholds,
) -> dict[str, Any]:
    scenario_checks: dict[str, dict[str, Any]] = {}
    all_pass = True

    for scenario_name in thresholds.required_stress_scenarios:
        scenario_metrics = stress_results.get(scenario_name, {}).get("metrics")
        if scenario_metrics is None:
            scenario_checks[scenario_name] = {"present": False, "passed": False}
            all_pass = False
            continue

        scenario_passed = (
            float(scenario_metrics["profit_factor"]) >= thresholds.min_stress_profit_factor
            and float(scenario_metrics["expectancy"]) > thresholds.min_stress_expectancy
        )
        scenario_checks[scenario_name] = {
            "present": True,
            "passed": scenario_passed,
            "profit_factor": float(scenario_metrics["profit_factor"]),
            "expectancy": float(scenario_metrics["expectancy"]),
        }
        all_pass = all_pass and scenario_passed

    return _gate(
        name="stressed_cost_survival",
        passed=all_pass,
        actual=scenario_checks,
        threshold={
            "required_scenarios": list(thresholds.required_stress_scenarios),
            "min_profit_factor": thresholds.min_stress_profit_factor,
            "min_expectancy": thresholds.min_stress_expectancy,
        },
        description="Promoted strategies must remain profitable after stressed and harsh execution assumptions.",
    )


def evaluate_promotion(
    aggregate_metrics: dict[str, Any],
    yearly_metrics: pd.DataFrame,
    stress_results: dict[str, dict[str, Any]],
    *,
    thresholds: PromotionThresholds | None = None,
    parameter_neighborhood: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or PromotionThresholds()
    metadata = metadata or {}

    dominant_year_share = compute_dominant_year_pnl_share(yearly_metrics)
    min_trades_per_year = int(yearly_metrics["total_trades"].min()) if not yearly_metrics.empty else 0

    gates = [
        _gate(
            name="minimum_total_trades",
            passed=int(aggregate_metrics["total_trades"]) >= thresholds.min_total_trades,
            actual=int(aggregate_metrics["total_trades"]),
            threshold=thresholds.min_total_trades,
            description="OOS trade count must be large enough to reduce false positives from thin samples.",
        ),
        _gate(
            name="minimum_trades_per_year",
            passed=(not yearly_metrics.empty) and min_trades_per_year >= thresholds.min_trades_per_year,
            actual=min_trades_per_year,
            threshold=thresholds.min_trades_per_year,
            description="Each covered year must contribute enough trades; one active year is not sufficient.",
        ),
        _gate(
            name="positive_expectancy_after_costs",
            passed=float(aggregate_metrics["expectancy"]) > thresholds.min_oos_expectancy,
            actual=float(aggregate_metrics["expectancy"]),
            threshold=thresholds.min_oos_expectancy,
            description="Average net PnL per trade must remain positive after modeled execution costs.",
        ),
        _gate(
            name="acceptable_max_drawdown",
            passed=float(aggregate_metrics["max_drawdown"]) <= thresholds.max_oos_drawdown,
            actual=float(aggregate_metrics["max_drawdown"]),
            threshold=thresholds.max_oos_drawdown,
            description="OOS drawdown must remain below a configured ceiling before promotion.",
        ),
        _gate(
            name="no_single_year_dominating_total_pnl",
            passed=dominant_year_share <= thresholds.max_single_year_pnl_share,
            actual=dominant_year_share,
            threshold=thresholds.max_single_year_pnl_share,
            description="A single positive year should not dominate the strategy's total OOS contribution.",
        ),
        _gate(
            name="oos_profit_factor_threshold",
            passed=float(aggregate_metrics["profit_factor"]) >= thresholds.min_oos_profit_factor,
            actual=float(aggregate_metrics["profit_factor"]),
            threshold=thresholds.min_oos_profit_factor,
            description="OOS profit factor must clear the configured promotion threshold.",
        ),
        _evaluate_parameter_neighborhood(parameter_neighborhood, thresholds),
        _evaluate_stress_survival(stress_results, thresholds),
    ]

    core_gate_names = {
        "minimum_total_trades",
        "minimum_trades_per_year",
        "positive_expectancy_after_costs",
        "acceptable_max_drawdown",
        "no_single_year_dominating_total_pnl",
        "oos_profit_factor_threshold",
        "stressed_cost_survival",
    }
    core_fail = any(gate["name"] in core_gate_names and gate["passed"] is False for gate in gates)
    core_pass = all(gate["name"] not in core_gate_names or gate["passed"] is True for gate in gates)
    neighborhood_pass = next(
        gate["passed"] for gate in gates if gate["name"] == "parameter_neighborhood_stability"
    )
    # Cross-pair evidence is an extra promotion input. Walk-forward alone is not enough
    # to classify a strategy as paper-trade ready.
    cross_pair_validated = _normalize_optional_bool(metadata.get("cross_pair_validated"), "cross_pair_validated")

    if core_fail:
        decision = "reject"
        promotion_status = "rejected"
    elif core_pass and neighborhood_pass is True and cross_pair_validated:
        decision = "paper_trade_candidate"
        promotion_status = "paper_trade_candidate"
    elif core_pass:
        decision = "continue"
        promotion_status = "walk_forward_validated"
    else:
        decision = "continue"
        promotion_status = "candidate"

    return {
        "decision": decision,
        "promotion_status": promotion_status,
        "thresholds": asdict(thresholds),
        "gates": gates,
        "metadata": metadata,
    }
