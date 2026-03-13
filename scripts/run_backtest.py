from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.backtest import run_backtest
from eurusd_quant.data.loaders import load_bars
from eurusd_quant.strategies.registry import STRATEGY_REGISTRY


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run EURUSD strategy backtest")
    parser.add_argument("--input", required=True, help="Path to input parquet bars")
    parser.add_argument("--strategy", required=True, help="Strategy key from config/strategies.yaml")
    parser.add_argument("--output-dir", required=True, help="Output directory for results")
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    args = parse_args()

    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    if args.strategy not in strategy_cfg_all or args.strategy not in STRATEGY_REGISTRY:
        supported = ", ".join(sorted(STRATEGY_REGISTRY))
        raise ValueError(f"Unsupported strategy: {args.strategy}. Supported strategies: {supported}")

    bars = load_bars(args.input)
    result = run_backtest(
        bars=bars,
        strategy_name=args.strategy,
        strategy_config=strategy_cfg_all[args.strategy],
        execution_config=execution_cfg,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades_path = output_dir / "trades.parquet"
    metrics_path = output_dir / "metrics.json"
    result.trades.to_parquet(trades_path, index=False)
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(result.metrics, f, indent=2)

    print("Backtest complete")
    print(f"Trades saved to: {trades_path}")
    print(f"Metrics saved to: {metrics_path}")
    for key, value in result.metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
