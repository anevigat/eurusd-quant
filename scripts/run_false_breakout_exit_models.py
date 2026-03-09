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
from eurusd_quant.strategies.false_breakout_reversal import (
    FalseBreakoutReversalConfig,
    FalseBreakoutReversalStrategy,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run false breakout exit-model experiments")
    parser.add_argument(
        "--input",
        default="data/bars/15m/eurusd_bars_15m_2023.parquet",
        help="Bars parquet input",
    )
    parser.add_argument(
        "--output-root",
        default="outputs/false_breakout_exit_models",
        help="Directory to store per-model outputs and summary",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def exit_reason_counts(trades: pd.DataFrame) -> dict[str, int]:
    labels = ["stop_loss", "take_profit", "time_exit", "flatten_intraday", "end_of_data"]
    counts = {label: int((trades["exit_reason"] == label).sum()) for label in labels}
    for label in sorted(set(trades["exit_reason"]) - set(labels)):
        counts[str(label)] = int((trades["exit_reason"] == label).sum())
    return counts


def build_model_metrics(trades: pd.DataFrame) -> dict:
    core = compute_metrics(trades)
    wins = trades.loc[trades["pnl_pips"] > 0, "pnl_pips"] if not trades.empty else pd.Series(dtype=float)
    losses = trades.loc[trades["pnl_pips"] < 0, "pnl_pips"] if not trades.empty else pd.Series(dtype=float)

    avg_win = float(wins.mean()) if not wins.empty else 0.0
    avg_loss = float(losses.mean()) if not losses.empty else 0.0
    median_win = float(wins.median()) if not wins.empty else 0.0
    median_loss = float(losses.median()) if not losses.empty else 0.0

    if avg_loss == 0.0:
        payoff_asymmetry = float("inf") if avg_win > 0 else 0.0
    else:
        payoff_asymmetry = abs(avg_win / avg_loss)

    return {
        "total_trades": int(core["total_trades"]),
        "win_rate": float(core["win_rate"]),
        "net_pnl": float(core["net_pnl"]),
        "expectancy": float(core["expectancy"]),
        "profit_factor": float(core["profit_factor"]),
        "max_drawdown": float(core["max_drawdown"]),
        "average_win_pips": avg_win,
        "average_loss_pips": avg_loss,
        "median_win_pips": median_win,
        "median_loss_pips": median_loss,
        "exit_reason_counts": exit_reason_counts(trades) if not trades.empty else {},
        "payoff_asymmetry": float(payoff_asymmetry),
    }


def run_model(
    bars: pd.DataFrame,
    execution_cfg: dict,
    base_strategy_cfg: dict,
    model: str,
    model_overrides: dict,
) -> tuple[pd.DataFrame, dict]:
    strategy_data = dict(base_strategy_cfg)
    strategy_data.update(
        {
            "allowed_side": "both",
            "entry_start_utc": "08:00",
            "entry_end_utc": "09:00",
            "exit_model": model,
        }
    )
    strategy_data.update(model_overrides)

    strategy = FalseBreakoutReversalStrategy(FalseBreakoutReversalConfig.from_dict(strategy_data))
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

    trades = simulator.get_trades_df()
    metrics = build_model_metrics(trades)
    return trades, metrics


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    if "false_breakout_reversal" not in strategy_cfg_all:
        raise ValueError("false_breakout_reversal strategy config not found")
    base_strategy_cfg = strategy_cfg_all["false_breakout_reversal"]

    bars = load_bars(args.input)

    models = [
        ("range_midpoint", {}),
        ("fixed_r", {"take_profit_r": 1.5}),
        ("atr_target", {"atr_target_multiple": 1.2}),
    ]

    all_results: list[dict] = []

    for model, overrides in models:
        run_dir = output_root / model
        run_dir.mkdir(parents=True, exist_ok=True)

        trades, metrics = run_model(
            bars=bars,
            execution_cfg=execution_cfg,
            base_strategy_cfg=base_strategy_cfg,
            model=model,
            model_overrides=overrides,
        )
        trades.to_parquet(run_dir / "trades.parquet", index=False)

        model_result = {
            "model": model,
            "overrides": overrides,
            "metrics": metrics,
            "output_dir": str(run_dir),
        }
        with (run_dir / "metrics.json").open("w", encoding="utf-8") as f:
            json.dump(model_result, f, indent=2)
        all_results.append(model_result)

    best_by_net = max(all_results, key=lambda r: r["metrics"]["net_pnl"])
    best_by_pf = max(all_results, key=lambda r: r["metrics"]["profit_factor"])
    best_by_payoff = max(all_results, key=lambda r: r["metrics"]["payoff_asymmetry"])

    summary = {
        "input": args.input,
        "fixed_configuration": {
            "strategy": "false_breakout_reversal",
            "allowed_side": "both",
            "entry_window_utc": "08:00-09:00",
        },
        "models": all_results,
        "best_by_net_pnl": best_by_net,
        "best_by_profit_factor": best_by_pf,
        "best_by_payoff_asymmetry": best_by_payoff,
    }
    with (output_root / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("False Breakout Exit-Model Results")
    for result in all_results:
        m = result["metrics"]
        print(
            f"- {result['model']}: trades={m['total_trades']}, win_rate={m['win_rate']:.4f}, "
            f"net_pnl={m['net_pnl']:.6f}, profit_factor={m['profit_factor']:.4f}, "
            f"payoff_asymmetry={m['payoff_asymmetry']:.4f}"
        )
    print(
        "Best by net_pnl: "
        f"{best_by_net['model']} ({best_by_net['metrics']['net_pnl']:.6f})"
    )
    print(
        "Best by profit_factor: "
        f"{best_by_pf['model']} ({best_by_pf['metrics']['profit_factor']:.4f})"
    )
    print(
        "Best payoff asymmetry: "
        f"{best_by_payoff['model']} ({best_by_payoff['metrics']['payoff_asymmetry']:.4f})"
    )
    print(f"Saved summary: {output_root / 'summary.json'}")


if __name__ == "__main__":
    main()
