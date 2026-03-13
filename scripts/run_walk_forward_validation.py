from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.data.loaders import load_bars
from eurusd_quant.validation import PromotionThresholds, run_walk_forward_validation


CONFIG_METADATA_COLUMNS = {
    "strategy",
    "strategy_name",
    "score",
    "rank",
    "notes",
    "config_hash",
    "profit_factor",
    "net_pnl",
    "expectancy",
    "win_rate",
    "max_drawdown",
    "trades",
    "total_trades",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run generic walk-forward validation for one or more strategy configs.")
    parser.add_argument("--strategy", required=True, help="Strategy key from config/strategies.yaml")
    parser.add_argument("--bars", required=True, help="Path to bars parquet")
    parser.add_argument("--train-years", type=int, default=3, help="Rolling train window size in years")
    parser.add_argument("--test-months", type=int, default=6, help="Rolling OOS window size in months")
    parser.add_argument("--embargo-days", type=int, default=0, help="Optional embargo gap between train and test windows")
    parser.add_argument("--output-dir", required=True, help="Output root for walk-forward runs")
    parser.add_argument("--input-configs", help="Optional CSV of configs to evaluate")
    parser.add_argument("--promotion-config", help="Optional YAML/JSON file overriding promotion thresholds")
    parser.add_argument("--top-n", type=int, help="Optional limit when --input-configs is provided")
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_structured_file(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return load_yaml(path)


def _coerce_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return json.loads(stripped)
        lowered = stripped.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        return stripped
    return value.item() if hasattr(value, "item") else value


def load_config_rows(
    strategy_name: str,
    strategy_config_all: dict[str, Any],
    input_configs_path: str | None,
    top_n: int | None,
) -> list[dict[str, Any]]:
    if input_configs_path is None:
        if strategy_name not in strategy_config_all:
            raise ValueError(f"Strategy config '{strategy_name}' not found in config/strategies.yaml")
        return [dict(strategy_config_all[strategy_name])]

    df = pd.read_csv(input_configs_path)
    if df.empty:
        raise ValueError("Input config CSV is empty")
    if top_n is not None:
        df = df.head(top_n)

    configs: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        row_dict = {key: _coerce_value(value) for key, value in row.items()}
        config_blob = row_dict.get("config_json") or row_dict.get("config")
        if isinstance(config_blob, dict):
            configs.append(config_blob)
            continue
        if isinstance(config_blob, str):
            configs.append(json.loads(config_blob))
            continue

        config = {
            key.removeprefix("param_"): value
            for key, value in row_dict.items()
            if key not in CONFIG_METADATA_COLUMNS
            and key not in {"config_json", "config", "parameter_neighborhood_json"}
            and value is not None
        }
        configs.append(config)
    return configs


def save_result(
    output_dir: Path,
    strategy_name: str,
    bars_path: str,
    strategy_config: dict[str, Any],
    result,
    *,
    train_years: int,
    test_months: int,
    embargo_days: int,
) -> None:
    run_dir = output_dir / result.config_hash
    run_dir.mkdir(parents=True, exist_ok=True)

    with (run_dir / "config.json").open("w", encoding="utf-8") as f:
        json.dump(strategy_config, f, indent=2, sort_keys=True)

    result.splits_df.to_csv(run_dir / "splits.csv", index=False)
    result.equity_curve.to_csv(run_dir / "equity_curve.csv", index=False)

    aggregate_payload = {
        "strategy": strategy_name,
        "bars": bars_path,
        "config_hash": result.config_hash,
        "train_years": train_years,
        "test_months": test_months,
        "embargo_days": embargo_days,
        "split_count": len(result.splits),
        "aggregate_oos_metrics": result.aggregate_metrics,
        "yearly_metrics": result.yearly_metrics.to_dict(orient="records"),
        "stress_test_metrics": result.stress_results,
    }
    with (run_dir / "aggregate.json").open("w", encoding="utf-8") as f:
        json.dump(aggregate_payload, f, indent=2, default=str)

    promotion_payload = {
        **result.promotion_report,
        "strategy": strategy_name,
        "bars": bars_path,
        "config_hash": result.config_hash,
        "aggregate_oos_metrics": result.aggregate_metrics,
        "yearly_metrics": result.yearly_metrics.to_dict(orient="records"),
        "stress_test_metrics": result.stress_results,
        "is_oos_ranges": [
            {
                "split_id": split.split_id,
                "train_start": split.train_start.isoformat(),
                "train_end": split.train_end.isoformat(),
                "test_start": split.test_start.isoformat(),
                "test_end": split.test_end.isoformat(),
            }
            for split in result.splits
        ],
    }
    with (run_dir / "promotion_report.json").open("w", encoding="utf-8") as f:
        json.dump(promotion_payload, f, indent=2, default=str)

    print(
        f"{result.config_hash} | splits={len(result.splits)} | "
        f"trades={result.aggregate_metrics['total_trades']} | "
        f"PF={result.aggregate_metrics['profit_factor']:.4f} | "
        f"decision={result.promotion_report['decision']}"
    )


def main() -> None:
    args = parse_args()

    bars = load_bars(args.bars)
    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    thresholds = (
        PromotionThresholds.from_dict(load_structured_file(Path(args.promotion_config)))
        if args.promotion_config
        else PromotionThresholds()
    )

    configs = load_config_rows(args.strategy, strategy_cfg_all, args.input_configs, args.top_n)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("config_hash | splits | trades | PF | decision")
    for strategy_config in configs:
        result = run_walk_forward_validation(
            bars=bars,
            strategy_name=args.strategy,
            strategy_config=strategy_config,
            execution_config=execution_cfg,
            train_years=args.train_years,
            test_months=args.test_months,
            embargo_days=args.embargo_days,
            thresholds=thresholds,
            metadata={"bars": args.bars, "strategy": args.strategy},
        )
        save_result(
            output_dir,
            args.strategy,
            args.bars,
            strategy_config,
            result,
            train_years=args.train_years,
            test_months=args.test_months,
            embargo_days=args.embargo_days,
        )


if __name__ == "__main__":
    main()
