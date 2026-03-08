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

WINDOWS = [
    ("07_08", "07:00", "08:00"),
    ("08_09", "08:00", "09:00"),
    ("09_10", "09:00", "10:00"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Session Breakout experiments by entry subwindow")
    parser.add_argument("--bars", required=True, help="Path to bars parquet")
    parser.add_argument("--strategy", default="session_breakout", help="Strategy key")
    parser.add_argument("--output-root", default="outputs/window_experiments", help="Output root directory")
    parser.add_argument(
        "--entry-window-mode",
        choices=["fixed_utc", "london_local"],
        default="fixed_utc",
        help="Entry window interpretation mode",
    )
    parser.add_argument("--run-stress", action="store_true", help="Run stress test for each subwindow")
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


def summarize_window(trades: pd.DataFrame, metrics: dict, pip_size: float) -> dict:
    long_count = int((trades["side"] == "long").sum()) if not trades.empty else 0
    short_count = int((trades["side"] == "short").sum()) if not trades.empty else 0
    avg_holding = float(trades["bars_held"].mean()) if not trades.empty else 0.0
    pnl_pips = float(metrics["net_pnl"] / pip_size) if pip_size > 0 else 0.0

    return {
        "total_trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "gross_pnl": float(metrics["gross_pnl"]),
        "net_pnl": float(metrics["net_pnl"]),
        "pnl_pips": pnl_pips,
        "expectancy": float(metrics["expectancy"]),
        "profit_factor": float(metrics["profit_factor"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "average_holding_bars": avg_holding,
        "long_trade_count": long_count,
        "short_trade_count": short_count,
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
    base_strategy_cfg["entry_window_mode"] = args.entry_window_mode

    pip_size = float(execution_cfg["pip_size"])
    comparison: dict[str, dict] = {}

    for label, start, end in WINDOWS:
        window_dir = output_root / label
        window_dir.mkdir(parents=True, exist_ok=True)

        strategy_cfg = dict(base_strategy_cfg)
        strategy_cfg["entry_start_utc"] = start
        strategy_cfg["entry_end_utc"] = end

        trades, metrics = run_backtest_once(bars, strategy_cfg, execution_cfg)
        trades.to_parquet(window_dir / "trades.parquet", index=False)
        with (window_dir / "metrics.json").open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        summary = summarize_window(trades, metrics, pip_size=pip_size)
        summary["stress_test_metrics"] = None

        if args.run_stress:
            stress_cfg = dict(execution_cfg)
            stress_cfg["market_slippage_pips"] = float(execution_cfg["market_slippage_pips"]) * 2.0
            stress_cfg["stop_slippage_pips"] = float(execution_cfg["stop_slippage_pips"]) * 2.0
            stress_cfg["fee_per_trade"] = float(execution_cfg["fee_per_trade"]) + (
                args.stress_spread_penalty_pips * pip_size
            )
            stress_trades, stress_metrics = run_backtest_once(bars, strategy_cfg, stress_cfg)
            stress_trades.to_parquet(window_dir / "stress_trades.parquet", index=False)
            with (window_dir / "stress_metrics.json").open("w", encoding="utf-8") as f:
                json.dump(stress_metrics, f, indent=2)
            summary["stress_test_metrics"] = stress_metrics

        comparison[label] = summary
        print(f"{label} done: trades={summary['total_trades']} net_pnl={summary['net_pnl']}")

    window_comparison = {
        "entry_window_mode": args.entry_window_mode,
        "stress_spread_penalty_pips": args.stress_spread_penalty_pips if args.run_stress else 0.0,
        "windows": comparison,
    }
    out_path = output_root / "window_comparison.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(window_comparison, f, indent=2)
    print(f"Saved comparison: {out_path}")


if __name__ == "__main__":
    main()
