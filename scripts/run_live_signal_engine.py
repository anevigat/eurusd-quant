from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.data.loaders import load_bars
from eurusd_quant.live.strategy_registry import get_strategy, list_strategies

DEFAULT_OUTPUT_DIR = "signals"
DEFAULT_LOG_DIR = "paper_trading_log"
DEFAULT_STRATEGY = "ny_impulse_mean_reversion"
DEFAULT_P90_THRESHOLD_PRICE = 0.002455


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live signal engine with strategy registry")
    parser.add_argument("--bars-file", required=True, help="Path to latest 15m bars parquet")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Signal JSON output directory")
    parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR, help="Paper trading log directory")
    parser.add_argument(
        "--strategy",
        default=DEFAULT_STRATEGY,
        help=f"Strategy name (default: {DEFAULT_STRATEGY})",
    )
    parser.add_argument(
        "--all-strategies",
        action="store_true",
        help="Evaluate all registered strategies",
    )
    parser.add_argument(
        "--p90-price-threshold",
        type=float,
        default=DEFAULT_P90_THRESHOLD_PRICE,
        help="Optional threshold override for NY impulse live adapter",
    )
    return parser.parse_args()


def format_file_ts(ts: pd.Timestamp) -> str:
    return ts.tz_convert("UTC").strftime("%Y-%m-%d_%H%M")


def append_signal_log(log_csv: Path, signal: dict) -> None:
    log_csv.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_csv.exists()

    row = {
        "timestamp": signal["timestamp"],
        "symbol": signal["symbol"],
        "strategy": signal["strategy"],
        "side": signal["side"],
        "entry": signal["entry_price"],
        "stop": signal["stop_price"],
        "target": signal["target_price"],
    }

    with log_csv.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["timestamp", "symbol", "strategy", "side", "entry", "stop", "target"],
        )
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def instantiate_strategy(strategy_name: str, p90_price_threshold: float):
    strategy_class = get_strategy(strategy_name)
    try:
        return strategy_class(p90_price_threshold=p90_price_threshold)
    except TypeError:
        return strategy_class()


def normalize_payload(signal: dict | None, strategy_name: str, timestamp: pd.Timestamp) -> dict:
    ts_str = timestamp.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    if signal is None:
        return {
            "timestamp": ts_str,
            "signal": "none",
        }

    # Keep simulator-compatible schema.
    return {
        "timestamp": signal.get("timestamp", ts_str),
        "strategy": signal.get("strategy", strategy_name),
        "symbol": signal["symbol"],
        "side": signal["side"],
        "entry_price": float(signal["entry_price"]),
        "stop_price": float(signal["stop_price"]),
        "target_price": float(signal["target_price"]),
        **{k: v for k, v in signal.items() if k not in {"timestamp", "strategy", "symbol", "side", "entry_price", "stop_price", "target_price"}},
    }


def main() -> None:
    args = parse_args()

    bars = load_bars(args.bars_file)
    if bars.empty:
        raise ValueError("Bars file is empty")

    latest_ts = pd.to_datetime(bars["timestamp"].iloc[-1], utc=True)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.all_strategies:
        strategy_names = list_strategies()
    else:
        strategy_names = [args.strategy]

    print(latest_ts.tz_convert("UTC").strftime("%Y-%m-%d %H:%M UTC"))

    for strategy_name in strategy_names:
        strategy = instantiate_strategy(strategy_name, args.p90_price_threshold)
        signal = strategy.evaluate_latest(bars)
        payload = normalize_payload(signal=signal, strategy_name=strategy_name, timestamp=latest_ts)

        if args.all_strategies:
            file_name = f"{format_file_ts(latest_ts)}_{strategy_name}.json"
        else:
            file_name = f"{format_file_ts(latest_ts)}.json"

        signal_file = output_dir / file_name
        with signal_file.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        if payload.get("signal") == "none":
            if args.all_strategies:
                print(f"[{strategy_name}] no signal")
            else:
                print("no signal")
            continue

        log_csv = Path(args.log_dir) / "signals_log.csv"
        append_signal_log(log_csv, payload)

        if args.all_strategies:
            print(f"[{strategy_name}] {'BUY' if payload['side'] == 'long' else 'SELL'} signal")
            print(f"entry: {payload['entry_price']:.4f}")
            print(f"stop: {payload['stop_price']:.4f}")
            print(f"target: {payload['target_price']:.4f}")
        else:
            print("NY impulse detected")
            print(f"{'BUY' if payload['side'] == 'long' else 'SELL'} signal")
            print(f"entry: {payload['entry_price']:.4f}")
            print(f"stop: {payload['stop_price']:.4f}")
            print(f"target: {payload['target_price']:.4f}")


if __name__ == "__main__":
    main()
