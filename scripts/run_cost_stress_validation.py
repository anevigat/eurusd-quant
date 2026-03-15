from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.data.loaders import load_bars
from eurusd_quant.validation import CostStressScenario, run_cost_stress_validation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run reusable cost-stress validation for a single strategy config")
    parser.add_argument("--strategy", required=True, help="Strategy key from config/strategies.yaml")
    parser.add_argument("--bars", required=True, help="Path to bars parquet")
    parser.add_argument("--output-dir", required=True, help="Output directory for scenario results")
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument("--config-json", help="Optional JSON object overriding the strategy config")
    config_group.add_argument("--config-file", help="Optional JSON/YAML file overriding the strategy config")
    parser.add_argument(
        "--spread-multipliers",
        default="1.0,1.5,2.0",
        help="Comma-separated spread multipliers to evaluate",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_structured_file(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = load_yaml(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Structured file '{path}' must decode to an object")
    return payload


def resolve_strategy_config(
    *,
    base_config: dict[str, Any],
    config_json: str | None,
    config_file: str | None,
) -> dict[str, Any]:
    if config_json is None and config_file is None:
        return dict(base_config)
    if config_json is not None:
        payload = json.loads(config_json)
        if not isinstance(payload, dict):
            raise ValueError("--config-json must decode to a JSON object")
        return dict(payload)
    return load_structured_file(Path(config_file))


def build_scenarios(spread_multipliers: str) -> list[CostStressScenario]:
    values = [float(value.strip()) for value in spread_multipliers.split(",") if value.strip()]
    if not values:
        raise ValueError("--spread-multipliers must contain at least one value")
    scenarios: list[CostStressScenario] = []
    for multiplier in values:
        if multiplier <= 0.0:
            raise ValueError("Spread multipliers must be positive")
        if multiplier == 1.0:
            name = "baseline"
        else:
            percentage = int(round((multiplier - 1.0) * 100))
            name = f"spread_plus_{percentage}"
        scenarios.append(CostStressScenario(name=name, spread_multiplier=multiplier))
    return scenarios


def main() -> None:
    args = parse_args()
    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    if args.strategy not in strategy_cfg_all:
        raise ValueError(f"Strategy config '{args.strategy}' not found in config/strategies.yaml")
    strategy_config = resolve_strategy_config(
        base_config=strategy_cfg_all[args.strategy],
        config_json=args.config_json,
        config_file=args.config_file,
    )
    bars = load_bars(args.bars)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scenarios = build_scenarios(args.spread_multipliers)
    results = run_cost_stress_validation(
        bars=bars,
        strategy_name=args.strategy,
        strategy_config=strategy_config,
        execution_config=execution_cfg,
        scenarios=scenarios,
    )

    for scenario_name, payload in results.items():
        scenario_dir = output_dir / scenario_name
        scenario_dir.mkdir(parents=True, exist_ok=True)
        with (scenario_dir / "metrics.json").open("w", encoding="utf-8") as handle:
            json.dump(payload["metrics"], handle, indent=2)
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "strategy": args.strategy,
                "bars": args.bars,
                "strategy_config": strategy_config,
                "results": results,
            },
            handle,
            indent=2,
        )

    for scenario_name, payload in results.items():
        metrics = payload["metrics"]
        print(
            f"{scenario_name} | trades={metrics['total_trades']} | PF={metrics['profit_factor']:.4f} | "
            f"net_pnl={metrics['net_pnl']:.6f} | max_dd={metrics['max_drawdown']:.6f}"
        )


if __name__ == "__main__":
    main()
