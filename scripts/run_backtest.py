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

from eurusd_quant.analytics.metrics import compute_metrics
from eurusd_quant.data.loaders import load_bars
from eurusd_quant.execution.simulator import ExecutionConfig, ExecutionSimulator
from eurusd_quant.strategies.session_breakout import SessionBreakoutConfig, SessionRangeBreakoutStrategy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run EURUSD Session Breakout backtest")
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
    if args.strategy not in strategy_cfg_all:
        raise ValueError(f"Unsupported strategy: {args.strategy}")
    if args.strategy != "session_breakout":
        raise ValueError("MVP only supports --strategy session_breakout")

    bars = load_bars(args.input)

    strategy_cfg = SessionBreakoutConfig.from_dict(strategy_cfg_all["session_breakout"])
    strategy = SessionRangeBreakoutStrategy(strategy_cfg)

    simulator = ExecutionSimulator(ExecutionConfig.from_dict(execution_cfg))

    for _, bar in bars.iterrows():
        simulator.process_bar(bar)
        order = strategy.generate_order(
            bar,
            has_open_position=simulator.has_open_position(),
            has_pending_order=simulator.has_pending_order(),
        )
        if order is not None:
            simulator.submit_order(order)

    if not bars.empty:
        simulator.close_open_position_at_end(bars.iloc[-1])

    trades_df = simulator.get_trades_df()
    metrics = compute_metrics(trades_df)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades_path = output_dir / "trades.parquet"
    metrics_path = output_dir / "metrics.json"
    trades_df.to_parquet(trades_path, index=False)
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print("Backtest complete")
    print(f"Trades saved to: {trades_path}")
    print(f"Metrics saved to: {metrics_path}")
    for key, value in metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
