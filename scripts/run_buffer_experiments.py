from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.analytics.metrics import compute_metrics
from eurusd_quant.data.loaders import load_bars
from eurusd_quant.execution.simulator import ExecutionConfig, ExecutionSimulator
from eurusd_quant.strategies.session_breakout import SessionBreakoutConfig, SessionRangeBreakoutStrategy

BUFFER_VALUES = [0.0, 0.1, 0.2, 0.3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run breakout buffer experiments for SessionRangeBreakoutStrategy")
    parser.add_argument("--bars", required=True, help="Path to bars parquet")
    parser.add_argument("--strategy", default="session_breakout", help="Strategy key from config/strategies.yaml")
    parser.add_argument("--output-root", default="outputs/buffer_experiments", help="Output root directory")
    parser.add_argument("--run-stress", action="store_true", help="Run stress metrics for each buffer")
    parser.add_argument(
        "--stress-spread-penalty-pips",
        type=float,
        default=0.0,
        help="Optional extra fee penalty in pips per trade for stress runs",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_backtest_once(bars: pd.DataFrame, strategy_cfg_dict: dict, execution_cfg_dict: dict) -> tuple[pd.DataFrame, dict]:
    strategy = SessionRangeBreakoutStrategy(SessionBreakoutConfig.from_dict(strategy_cfg_dict))
    simulator = ExecutionSimulator(ExecutionConfig.from_dict(execution_cfg_dict))

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

    trades = simulator.get_trades_df()
    metrics = compute_metrics(trades)
    return trades, metrics


def summarize(trades: pd.DataFrame, metrics: dict, pip_size: float) -> dict:
    return {
        "total_trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "profit_factor": float(metrics["profit_factor"]),
        "expectancy": float(metrics["expectancy"]),
        "pnl_pips": float(metrics["net_pnl"] / pip_size) if pip_size > 0 else 0.0,
        "max_drawdown": float(metrics["max_drawdown"]),
    }


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars)
    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    if args.strategy not in strategy_cfg_all:
        raise ValueError(f"Unsupported strategy: {args.strategy}")

    base_strategy_cfg = dict(strategy_cfg_all[args.strategy])
    base_strategy_cfg["entry_start_utc"] = "07:00"
    base_strategy_cfg["entry_end_utc"] = "08:00"

    pip_size = float(execution_cfg["pip_size"])
    comparison: dict[str, dict] = {}

    for buffer in BUFFER_VALUES:
        label = str(buffer).replace(".", "_")
        run_dir = output_root / label
        run_dir.mkdir(parents=True, exist_ok=True)

        strategy_cfg = dict(base_strategy_cfg)
        strategy_cfg["breakout_buffer_atr"] = buffer

        trades, metrics = run_backtest_once(bars, strategy_cfg, execution_cfg)
        trades.to_parquet(run_dir / "trades.parquet", index=False)
        with (run_dir / "metrics.json").open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        result = summarize(trades, metrics, pip_size)
        result["stress_test_metrics"] = None

        if args.run_stress:
            stress_cfg = dict(execution_cfg)
            stress_cfg["market_slippage_pips"] = float(execution_cfg["market_slippage_pips"]) * 2.0
            stress_cfg["stop_slippage_pips"] = float(execution_cfg["stop_slippage_pips"]) * 2.0
            stress_cfg["fee_per_trade"] = float(execution_cfg["fee_per_trade"]) + (
                args.stress_spread_penalty_pips * pip_size
            )
            _, stress_metrics = run_backtest_once(bars, strategy_cfg, stress_cfg)
            with (run_dir / "stress_metrics.json").open("w", encoding="utf-8") as f:
                json.dump(stress_metrics, f, indent=2)
            result["stress_test_metrics"] = stress_metrics

        comparison[f"{buffer:.1f}"] = result
        print(f"buffer={buffer:.1f} trades={result['total_trades']} pnl_pips={result['pnl_pips']:.2f}")

    out_path = output_root / "buffer_comparison.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "window_utc": "07:00-08:00",
                "stress_spread_penalty_pips": args.stress_spread_penalty_pips if args.run_stress else 0.0,
                "buffers": comparison,
            },
            f,
            indent=2,
        )
    print(f"Saved comparison: {out_path}")


if __name__ == "__main__":
    main()
