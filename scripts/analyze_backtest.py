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
from eurusd_quant.data.sessions import in_time_window, parse_hhmm
from eurusd_quant.execution.simulator import ExecutionConfig, ExecutionSimulator
from eurusd_quant.strategies.session_breakout import SessionBreakoutConfig, SessionRangeBreakoutStrategy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze backtest diagnostics and robustness")
    parser.add_argument("--trades", required=True, help="Path to trades parquet")
    parser.add_argument("--metrics", required=True, help="Path to baseline metrics json")
    parser.add_argument("--bars", required=True, help="Path to bars parquet used for the backtest")
    parser.add_argument("--strategy", default="session_breakout", help="Strategy key from config/strategies.yaml")
    parser.add_argument("--output-dir", default="outputs/diagnostics", help="Directory for diagnostic outputs")
    parser.add_argument(
        "--stress-spread-penalty-pips",
        type=float,
        default=0.0,
        help="Optional extra stress penalty applied per trade in pips",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_trades(trades: pd.DataFrame, pip_size: float) -> pd.DataFrame:
    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"], utc=True)
    out["signal_time"] = pd.to_datetime(out["signal_time"], utc=True)
    out["exit_time"] = pd.to_datetime(out["exit_time"], utc=True)
    if "pnl_pips" not in out.columns:
        out["pnl_pips"] = out["net_pnl"] / pip_size
    out["entry_month"] = out["entry_time"].dt.strftime("%Y-%m")
    out["entry_hour"] = out["entry_time"].dt.hour
    return out


def build_monthly_stats(trades: pd.DataFrame) -> pd.DataFrame:
    grouped = trades.groupby("entry_month")
    out = grouped.agg(
        trades=("entry_month", "size"),
        win_rate=("net_pnl", lambda s: float((s > 0).mean()) if len(s) else 0.0),
        pnl=("net_pnl", "sum"),
    )
    return out.reset_index().sort_values("entry_month")


def build_hourly_stats(trades: pd.DataFrame) -> pd.DataFrame:
    grouped = trades.groupby("entry_hour")
    out = grouped.agg(
        trades=("entry_hour", "size"),
        win_rate=("net_pnl", lambda s: float((s > 0).mean()) if len(s) else 0.0),
        pnl=("net_pnl", "sum"),
    )
    return out.reset_index().sort_values("entry_hour")


def run_backtest_for_config(bars: pd.DataFrame, strategy_key: str, execution_cfg: dict, strategy_cfg_all: dict) -> dict:
    if strategy_key not in strategy_cfg_all:
        raise ValueError(f"Unsupported strategy: {strategy_key}")
    if strategy_key != "session_breakout":
        raise ValueError("Diagnostics MVP only supports session_breakout")

    strategy_cfg = SessionBreakoutConfig.from_dict(strategy_cfg_all[strategy_key])
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

    stress_trades = simulator.get_trades_df()
    stress_metrics = compute_metrics(stress_trades)
    return {"trades": stress_trades, "metrics": stress_metrics}


def main() -> None:
    args = parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    pip_size = float(execution_cfg["pip_size"])

    baseline_metrics = load_json(Path(args.metrics))
    bars = load_bars(args.bars)
    trades = pd.read_parquet(args.trades)
    trades = normalize_trades(trades, pip_size=pip_size)

    monthly = build_monthly_stats(trades)
    hourly = build_hourly_stats(trades)

    exit_reasons = ["stop_loss", "take_profit", "time_exit", "flatten_intraday", "end_of_data"]
    exit_reason_counts = {reason: int((trades["exit_reason"] == reason).sum()) for reason in exit_reasons}

    long_mask = trades["side"] == "long"
    short_mask = trades["side"] == "short"

    avg_win_pips = float(trades.loc[trades["pnl_pips"] > 0, "pnl_pips"].mean()) if (trades["pnl_pips"] > 0).any() else 0.0
    avg_loss_pips = float(trades.loc[trades["pnl_pips"] < 0, "pnl_pips"].mean()) if (trades["pnl_pips"] < 0).any() else 0.0
    average_holding_bars = float(trades["bars_held"].mean()) if len(trades) else 0.0

    monthly_pnl = monthly.set_index("entry_month")["pnl"]
    abs_monthly_pnl_sum = float(monthly_pnl.abs().sum())
    top2_share = 0.0
    if abs_monthly_pnl_sum > 0:
        top2_share = float(monthly_pnl.abs().sort_values(ascending=False).head(2).sum() / abs_monthly_pnl_sum)
    pnl_concentrated = top2_share > 0.7

    entry_start = parse_hhmm(strategy_cfg_all[args.strategy]["entry_start_utc"])
    entry_end = parse_hhmm(strategy_cfg_all[args.strategy]["entry_end_utc"])
    in_window_count = int(sum(in_time_window(ts, entry_start, entry_end) for ts in trades["entry_time"]))
    in_window_ratio = float(in_window_count / len(trades)) if len(trades) else 0.0

    monthly_path = output_dir / "monthly_pnl.csv"
    hourly_path = output_dir / "hourly_stats.csv"
    summary_path = output_dir / "summary.json"
    stress_path = output_dir / "stress_test_metrics.json"

    monthly.to_csv(monthly_path, index=False)
    hourly.to_csv(hourly_path, index=False)

    stress_execution_cfg = dict(execution_cfg)
    stress_execution_cfg["market_slippage_pips"] = float(execution_cfg["market_slippage_pips"]) * 2.0
    stress_execution_cfg["stop_slippage_pips"] = float(execution_cfg["stop_slippage_pips"]) * 2.0
    stress_execution_cfg["fee_per_trade"] = float(execution_cfg["fee_per_trade"]) + (
        args.stress_spread_penalty_pips * pip_size
    )

    stress_result = run_backtest_for_config(
        bars=bars,
        strategy_key=args.strategy,
        execution_cfg=stress_execution_cfg,
        strategy_cfg_all=strategy_cfg_all,
    )
    stress_metrics = stress_result["metrics"]
    stress_metrics["stress_spread_penalty_pips"] = args.stress_spread_penalty_pips
    with stress_path.open("w", encoding="utf-8") as f:
        json.dump(stress_metrics, f, indent=2)

    profitability_survives_stress = bool(stress_metrics["net_pnl"] > 0 and stress_metrics["profit_factor"] > 1.0)

    summary = {
        "baseline_metrics": baseline_metrics,
        "stress_test_metrics": stress_metrics,
        "trades_analyzed": int(len(trades)),
        "trades_per_month": {str(r["entry_month"]): int(r["trades"]) for _, r in monthly.iterrows()},
        "win_rate_by_month": {str(r["entry_month"]): float(r["win_rate"]) for _, r in monthly.iterrows()},
        "pnl_by_month": {str(r["entry_month"]): float(r["pnl"]) for _, r in monthly.iterrows()},
        "trades_by_entry_hour": {str(int(r["entry_hour"])): int(r["trades"]) for _, r in hourly.iterrows()},
        "pnl_by_entry_hour": {str(int(r["entry_hour"])): float(r["pnl"]) for _, r in hourly.iterrows()},
        "average_holding_bars": average_holding_bars,
        "average_win_pips": avg_win_pips,
        "average_loss_pips": avg_loss_pips,
        "long_trade_count": int(long_mask.sum()),
        "short_trade_count": int(short_mask.sum()),
        "long_pnl": float(trades.loc[long_mask, "net_pnl"].sum()),
        "short_pnl": float(trades.loc[short_mask, "net_pnl"].sum()),
        "exit_reason_counts": exit_reason_counts,
        "pnl_concentration_top2_share": top2_share,
        "pnl_concentrated_in_few_months": pnl_concentrated,
        "entry_window_adherence_ratio": in_window_ratio,
        "profitability_survives_stress": profitability_survives_stress,
    }

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("Diagnostics complete")
    print(f"Summary: {summary_path}")
    print(f"Monthly stats: {monthly_path}")
    print(f"Hourly stats: {hourly_path}")
    print(f"Stress metrics: {stress_path}")
    print("")
    print("Baseline metrics")
    for key, value in baseline_metrics.items():
        print(f"{key}: {value}")
    print("")
    print("Stress test metrics")
    for key, value in stress_metrics.items():
        print(f"{key}: {value}")
    print("")
    print(f"Profitability survives stress: {profitability_survives_stress}")
    print(f"PnL concentrated in few months: {pnl_concentrated} (top2 share={top2_share:.2%})")
    print(f"Trades in intended entry window: {in_window_count}/{len(trades)} ({in_window_ratio:.2%})")


if __name__ == "__main__":
    main()
