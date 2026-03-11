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
from eurusd_quant.strategies.ny_impulse_mean_reversion import (
    NYImpulseMeanReversionConfig,
    NYImpulseMeanReversionStrategy,
)

DEFAULT_INPUT = "data/bars/15m/eurusd_bars_15m_2018_2024.parquet"
DEFAULT_OUTPUT_ROOT = "outputs/ny_impulse_execution_stress"
DEFAULT_P90_PRICE_THRESHOLD = 0.002455


SCENARIOS = (
    "baseline",
    "spread_x2",
    "slippage_1pip",
    "slippage_2pip",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NY impulse execution stress tests.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Bars parquet input")
    parser.add_argument(
        "--output-root",
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory for scenario outputs and summary",
    )
    parser.add_argument(
        "--p90-price-threshold",
        type=float,
        default=DEFAULT_P90_PRICE_THRESHOLD,
        help="Fixed p90 impulse threshold in price units",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_once(bars: pd.DataFrame, strategy_cfg: dict, execution_cfg: dict) -> pd.DataFrame:
    strategy = NYImpulseMeanReversionStrategy(NYImpulseMeanReversionConfig.from_dict(strategy_cfg))
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

    return simulator.get_trades_df()


def double_spread_bars(bars: pd.DataFrame) -> pd.DataFrame:
    stressed = bars.copy()
    for suffix in ("open", "high", "low", "close"):
        bid_col = f"bid_{suffix}"
        ask_col = f"ask_{suffix}"
        spread_col = f"spread_{suffix}"

        mid = (stressed[bid_col] + stressed[ask_col]) / 2.0
        spread = stressed[ask_col] - stressed[bid_col]

        stressed[bid_col] = mid - spread
        stressed[ask_col] = mid + spread
        stressed[spread_col] = stressed[ask_col] - stressed[bid_col]

    return stressed


def apply_uniform_exit_slippage(trades: pd.DataFrame, slippage_pips: float, pip_size: float) -> pd.DataFrame:
    if trades.empty or slippage_pips <= 0:
        return trades

    stressed = trades.copy()
    penalty = slippage_pips * pip_size
    non_stop_mask = stressed["exit_reason"] != "stop_loss"

    stressed.loc[non_stop_mask, "gross_pnl"] -= penalty
    stressed.loc[non_stop_mask, "net_pnl"] -= penalty
    stressed.loc[non_stop_mask, "pnl_pips"] -= slippage_pips
    stressed.loc[non_stop_mask, "slippage_cost"] += penalty

    return stressed


def scenario_overrides(scenario: str, execution_cfg: dict, bars: pd.DataFrame) -> tuple[dict, pd.DataFrame, float]:
    cfg = dict(execution_cfg)
    scenario_bars = bars
    uniform_exit_slippage_pips = 0.0

    if scenario == "baseline":
        return cfg, scenario_bars, uniform_exit_slippage_pips

    if scenario == "spread_x2":
        scenario_bars = double_spread_bars(bars)
        return cfg, scenario_bars, uniform_exit_slippage_pips

    if scenario == "slippage_1pip":
        cfg["market_slippage_pips"] = 1.0
        cfg["stop_slippage_pips"] = 1.0
        uniform_exit_slippage_pips = 1.0
        return cfg, scenario_bars, uniform_exit_slippage_pips

    if scenario == "slippage_2pip":
        cfg["market_slippage_pips"] = 2.0
        cfg["stop_slippage_pips"] = 2.0
        uniform_exit_slippage_pips = 2.0
        return cfg, scenario_bars, uniform_exit_slippage_pips

    raise ValueError(f"Unsupported scenario: {scenario}")


def summarize(scenario: str, metrics: dict, pip_size: float) -> dict:
    return {
        "scenario": scenario,
        "total_trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "profit_factor": float(metrics["profit_factor"]),
        "net_pnl": float(metrics["net_pnl"]),
        "expectancy": float(metrics["expectancy"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "avg_win_pips": float(metrics["average_win"] / pip_size) if pip_size > 0 else 0.0,
        "avg_loss_pips": float(metrics["average_loss"] / pip_size) if pip_size > 0 else 0.0,
    }


def main() -> None:
    args = parse_args()

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.input)
    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategies_cfg = load_yaml(ROOT / "config" / "strategies.yaml")

    if "ny_impulse_mean_reversion" not in strategies_cfg:
        raise ValueError("Strategy config 'ny_impulse_mean_reversion' not found")

    pip_size = float(execution_cfg["pip_size"])
    threshold_pips = float(args.p90_price_threshold) / pip_size

    # Frozen baseline strategy configuration (entry logic unchanged).
    strategy_cfg = dict(strategies_cfg["ny_impulse_mean_reversion"])
    strategy_cfg["impulse_threshold_pips"] = threshold_pips
    strategy_cfg["retracement_entry_ratio"] = 0.50
    strategy_cfg["exit_model"] = "atr"
    strategy_cfg["atr_target_multiple"] = 1.0

    results: list[dict] = []
    print("scenario | trades | win_rate | PF | net_pnl | max_dd")

    for scenario in SCENARIOS:
        scenario_dir = output_root / scenario
        scenario_dir.mkdir(parents=True, exist_ok=True)

        execution_override, scenario_bars, uniform_exit_slippage_pips = scenario_overrides(
            scenario=scenario,
            execution_cfg=execution_cfg,
            bars=bars,
        )

        trades = run_once(
            bars=scenario_bars,
            strategy_cfg=strategy_cfg,
            execution_cfg=execution_override,
        )

        trades = apply_uniform_exit_slippage(
            trades,
            slippage_pips=uniform_exit_slippage_pips,
            pip_size=pip_size,
        )

        metrics = compute_metrics(trades)

        trades.to_parquet(scenario_dir / "trades.parquet", index=False)
        with (scenario_dir / "metrics.json").open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        row = summarize(scenario=scenario, metrics=metrics, pip_size=pip_size)
        results.append(row)

        print(
            f"{row['scenario']:>13} | {row['total_trades']:>6} | {row['win_rate']:.4f} | "
            f"{row['profit_factor']:.4f} | {row['net_pnl']:.6f} | {row['max_drawdown']:.6f}"
        )

    summary = {
        "strategy": "ny_impulse_mean_reversion",
        "input": args.input,
        "fixed_configuration": {
            "impulse_threshold_price": float(args.p90_price_threshold),
            "impulse_threshold_pips": float(threshold_pips),
            "retracement_entry_ratio": 0.50,
            "exit_model": "atr",
            "atr_target_multiple": 1.0,
        },
        "results": results,
    }

    summary_path = output_root / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved summary: {summary_path}")


if __name__ == "__main__":
    main()
