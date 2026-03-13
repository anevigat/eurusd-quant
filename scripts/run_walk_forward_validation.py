from __future__ import annotations

import argparse
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ConfigExecutionRequest:
    strategy_config: dict[str, Any]
    metadata: dict[str, Any]
    parameter_neighborhood: dict[str, Any] | None
    config_identifier: str


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
    "cross_pair_validated",
    "parameter_neighborhood_json",
    "parameter_neighborhood",
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
    parser.add_argument(
        "--cross-pair-validated",
        choices=["true", "false"],
        help="Optional global cross-pair validation flag passed into promotion metadata",
    )
    parser.add_argument(
        "--promotion-metadata-json",
        help="Optional JSON file with additional promotion metadata, such as cross_pair_validated or parameter_neighborhood",
    )
    parser.add_argument("--top-n", type=int, help="Optional limit when --input-configs is provided")
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_structured_file(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    else:
        payload = load_yaml(path)

    if not isinstance(payload, dict):
        raise ValueError(f"Structured file '{path}' must decode to a JSON/YAML object")
    return payload


def _parse_optional_bool(value: Any, field_name: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "none"}:
            return None
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    raise ValueError(f"{field_name} must be true, false, or omitted")


def _parse_optional_json_dict(value: Any, field_name: str, context: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} for {context} must be a JSON object")

    stripped = value.strip()
    if not stripped:
        return None

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {field_name} for {context}: {exc.msg}") from exc

    if parsed is None:
        return None
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} for {context} must decode to a JSON object")
    return parsed


def _parse_required_json_dict(value: Any, field_name: str, context: str) -> dict[str, Any]:
    parsed = _parse_optional_json_dict(value, field_name, context)
    if parsed is None:
        raise ValueError(f"{field_name} for {context} must be a non-empty JSON object")
    return parsed


def _config_identifier(row_index: int, row_dict: dict[str, Any]) -> str:
    config_id = row_dict.get("config_hash")
    if config_id not in {None, ""}:
        return f"row {row_index} (config_hash={config_id})"
    rank = row_dict.get("rank")
    if rank not in {None, ""}:
        return f"row {row_index} (rank={rank})"
    return f"row {row_index}"


def _sanitize_strategy_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in config.items()
        if key not in CONFIG_METADATA_COLUMNS and value is not None
    }


def _coerce_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        lowered = stripped.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        return stripped
    return value.item() if hasattr(value, "item") else value


def build_base_promotion_metadata(
    *,
    cross_pair_validated: str | None,
    promotion_metadata_path: str | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    cross_pair = _parse_optional_bool(cross_pair_validated, "cross_pair_validated")
    if cross_pair is not None:
        metadata["cross_pair_validated"] = cross_pair

    if promotion_metadata_path is not None:
        metadata.update(load_structured_file(Path(promotion_metadata_path)))
    return metadata


def load_config_requests(
    strategy_name: str,
    strategy_config_all: dict[str, Any],
    input_configs_path: str | None,
    top_n: int | None,
    *,
    base_metadata: dict[str, Any] | None = None,
) -> list[ConfigExecutionRequest]:
    base_metadata = dict(base_metadata or {})

    if input_configs_path is None:
        if strategy_name not in strategy_config_all:
            raise ValueError(f"Strategy config '{strategy_name}' not found in config/strategies.yaml")
        parameter_neighborhood = _parse_optional_json_dict(
            base_metadata.get("parameter_neighborhood"),
            "parameter_neighborhood",
            "global promotion metadata",
        )
        return [
            ConfigExecutionRequest(
                strategy_config=_sanitize_strategy_config(dict(strategy_config_all[strategy_name])),
                metadata=base_metadata,
                parameter_neighborhood=parameter_neighborhood,
                config_identifier="default_config",
            )
        ]

    df = pd.read_csv(input_configs_path)
    if df.empty:
        raise ValueError("Input config CSV is empty")
    if top_n is not None:
        df = df.head(top_n)

    requests: list[ConfigExecutionRequest] = []
    for row_index, row in df.iterrows():
        row_dict = {key: _coerce_value(value) for key, value in row.items()}
        context = _config_identifier(row_index, row_dict)
        config_blob = row_dict.get("config_json") or row_dict.get("config")
        if config_blob is not None:
            strategy_config = _sanitize_strategy_config(
                _parse_required_json_dict(config_blob, "config_json", context)
            )
        else:
            strategy_config = _sanitize_strategy_config(
                {
                    key.removeprefix("param_"): value
                    for key, value in row_dict.items()
                    if key not in CONFIG_METADATA_COLUMNS
                    and key not in {"config_json", "config"}
                    and value is not None
                }
            )

        metadata = dict(base_metadata)
        row_cross_pair = _parse_optional_bool(row_dict.get("cross_pair_validated"), "cross_pair_validated")
        if row_cross_pair is not None:
            metadata["cross_pair_validated"] = row_cross_pair

        row_parameter_neighborhood = _parse_optional_json_dict(
            row_dict.get("parameter_neighborhood_json"),
            "parameter_neighborhood_json",
            context,
        )
        if row_parameter_neighborhood is not None:
            metadata["parameter_neighborhood"] = row_parameter_neighborhood

        parameter_neighborhood = _parse_optional_json_dict(
            metadata.get("parameter_neighborhood"),
            "parameter_neighborhood",
            context,
        )
        requests.append(
            ConfigExecutionRequest(
                strategy_config=strategy_config,
                metadata=metadata,
                parameter_neighborhood=parameter_neighborhood,
                config_identifier=context,
            )
        )
    return requests


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
    base_metadata = build_base_promotion_metadata(
        cross_pair_validated=args.cross_pair_validated,
        promotion_metadata_path=args.promotion_metadata_json,
    )

    requests = load_config_requests(
        args.strategy,
        strategy_cfg_all,
        args.input_configs,
        args.top_n,
        base_metadata=base_metadata,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("config_hash | splits | trades | PF | decision")
    for request in requests:
        request_metadata = {
            "bars": args.bars,
            "strategy": args.strategy,
            **request.metadata,
        }
        result = run_walk_forward_validation(
            bars=bars,
            strategy_name=args.strategy,
            strategy_config=request.strategy_config,
            execution_config=execution_cfg,
            train_years=args.train_years,
            test_months=args.test_months,
            embargo_days=args.embargo_days,
            thresholds=thresholds,
            parameter_neighborhood=request.parameter_neighborhood,
            metadata=request_metadata,
        )
        save_result(
            output_dir,
            args.strategy,
            args.bars,
            request.strategy_config,
            result,
            train_years=args.train_years,
            test_months=args.test_months,
            embargo_days=args.embargo_days,
        )


if __name__ == "__main__":
    main()
