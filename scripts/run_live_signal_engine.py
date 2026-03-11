from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.data.loaders import load_bars
from eurusd_quant.data.sessions import in_time_window, parse_hhmm
from eurusd_quant.strategies.ny_impulse_mean_reversion import (
    NYImpulseMeanReversionConfig,
    NYImpulseMeanReversionStrategy,
)

DEFAULT_OUTPUT_DIR = "signals"
DEFAULT_LOG_DIR = "paper_trading_log"
DEFAULT_P90_THRESHOLD_PRICE = 0.002455


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live signal engine for NY impulse mean reversion.")
    parser.add_argument("--bars-file", required=True, help="Path to latest 15m bars parquet")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Signal JSON output directory")
    parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR, help="Paper trading log directory")
    parser.add_argument(
        "--p90-price-threshold",
        type=float,
        default=DEFAULT_P90_THRESHOLD_PRICE,
        help="P90 impulse threshold in price units",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def iso_utc(ts: pd.Timestamp) -> str:
    return ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def format_file_ts(ts: pd.Timestamp) -> str:
    return ts.tz_convert("UTC").strftime("%Y-%m-%d_%H%M")


def compute_impulse_size(today_bars: pd.DataFrame, impulse_start: str, impulse_end: str) -> float:
    start_t = parse_hhmm(impulse_start)
    end_t = parse_hhmm(impulse_end)
    impulse_bars = today_bars[today_bars["timestamp"].apply(lambda t: in_time_window(t, start_t, end_t))]
    if impulse_bars.empty:
        return 0.0
    return float(impulse_bars["mid_high"].max() - impulse_bars["mid_low"].min())


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


def main() -> None:
    args = parse_args()

    bars = load_bars(args.bars_file)
    if bars.empty:
        raise ValueError("Bars file is empty")

    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategies_cfg = load_yaml(ROOT / "config" / "strategies.yaml")

    if "ny_impulse_mean_reversion" not in strategies_cfg:
        raise ValueError("Strategy config 'ny_impulse_mean_reversion' not found")

    pip_size = float(execution_cfg["pip_size"])
    threshold_pips = float(args.p90_price_threshold) / pip_size

    # Frozen validated configuration for paper trading.
    strategy_cfg = dict(strategies_cfg["ny_impulse_mean_reversion"])
    strategy_cfg["impulse_threshold_pips"] = threshold_pips
    strategy_cfg["retracement_entry_ratio"] = 0.50
    strategy_cfg["exit_model"] = "atr"
    strategy_cfg["atr_target_multiple"] = 1.0

    strategy = NYImpulseMeanReversionStrategy(NYImpulseMeanReversionConfig.from_dict(strategy_cfg))

    latest_ts = bars["timestamp"].iloc[-1]
    today = latest_ts.date()
    today_bars = bars[bars["timestamp"].dt.date == today].copy()

    latest_order = None
    for _, bar in today_bars.iterrows():
        order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
        if bar["timestamp"] == latest_ts:
            latest_order = order

    impulse_size = compute_impulse_size(
        today_bars,
        impulse_start=strategy_cfg["impulse_start_utc"],
        impulse_end=strategy_cfg["impulse_end_utc"],
    )
    impulse_threshold = float(strategy_cfg["impulse_threshold_pips"] * pip_size)

    if latest_order is None:
        signal_payload = {
            "timestamp": iso_utc(latest_ts),
            "signal": "none",
        }
    else:
        signal_payload = {
            "timestamp": iso_utc(latest_ts),
            "strategy": "ny_impulse_mean_reversion",
            "symbol": latest_order.symbol,
            "side": latest_order.side,
            "entry_price": float(latest_order.entry_reference),
            "stop_price": float(latest_order.stop_loss),
            "target_price": float(latest_order.take_profit),
            "impulse_size": impulse_size,
            "impulse_threshold": impulse_threshold,
        }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    signal_file = output_dir / f"{format_file_ts(latest_ts)}.json"

    with signal_file.open("w", encoding="utf-8") as f:
        json.dump(signal_payload, f, indent=2)

    if latest_order is not None:
        log_csv = Path(args.log_dir) / "signals_log.csv"
        append_signal_log(log_csv, signal_payload)

    print(latest_ts.tz_convert("UTC").strftime("%Y-%m-%d %H:%M UTC"))
    if latest_order is None:
        print("no signal")
    else:
        print("NY impulse detected")
        print(f"{'BUY' if latest_order.side == 'long' else 'SELL'} signal")
        print(f"entry: {latest_order.entry_reference:.4f}")
        print(f"stop: {latest_order.stop_loss:.4f}")
        print(f"target: {latest_order.take_profit:.4f}")


if __name__ == "__main__":
    main()
