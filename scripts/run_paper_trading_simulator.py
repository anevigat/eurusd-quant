from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]

OPEN_COLS = [
    "timestamp",
    "symbol",
    "strategy",
    "side",
    "entry_price",
    "stop_price",
    "target_price",
]
CLOSED_COLS = [
    "entry_time",
    "exit_time",
    "symbol",
    "strategy",
    "side",
    "entry_price",
    "exit_price",
    "pnl_pips",
    "pnl",
    "exit_reason",
]
EQUITY_COLS = ["timestamp", "equity"]
EXECUTION_LOG_COLS = ["timestamp", "event", "strategy", "symbol", "message"]
LAYOUT_DIRS = ("signals", "state", "logs", "reports")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run paper trading simulator from live signal files")
    parser.add_argument(
        "--signals-dir",
        default="paper_trading/signals",
        help="Directory with signal JSON files",
    )
    parser.add_argument(
        "--bars-file",
        default="data/bars/15m/eurusd_bars_latest.parquet",
        help="Latest bars parquet used for stop/target checks",
    )
    parser.add_argument(
        "--state-dir",
        default="paper_trading/state",
        help="Directory for open/closed positions and equity state",
    )
    parser.add_argument(
        "--log-dir",
        default="paper_trading/logs",
        help="Directory for execution logs",
    )
    return parser.parse_args()


def load_pip_size() -> float:
    cfg_path = ROOT / "config" / "execution.yaml"
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return float(cfg["pip_size"])


def read_csv_or_empty(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(path)
    for col in columns:
        if col not in df.columns:
            df[col] = pd.NA
    return df[columns].copy()


def write_csv(df: pd.DataFrame, path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    if out.empty:
        out = pd.DataFrame(columns=columns)
    else:
        out = out[columns]
    out.to_csv(path, index=False)


def infer_layout_root(*paths: Path) -> Path:
    for path in paths:
        if path.name in LAYOUT_DIRS:
            return path.parent
    return Path("paper_trading")


def ensure_paper_trading_layout(root: Path) -> None:
    for name in LAYOUT_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)


def append_execution_log(log_file: Path, rows: list[dict]) -> None:
    if not rows:
        return
    log_file.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_file.exists()
    with log_file.open("a", newline="", encoding="utf-8") as f:
        writer = pd.DataFrame(rows, columns=EXECUTION_LOG_COLS)
        writer.to_csv(f, header=write_header, index=False)


def latest_signal_file(signals_dir: Path) -> Path | None:
    if not signals_dir.exists():
        return None
    files = sorted(signals_dir.glob("*.json"))
    return files[-1] if files else None


def load_signal(path: Path) -> dict:
    return pd.read_json(path, typ="series").to_dict()


def price_hit_for_long(bar: pd.Series, stop: float, target: float) -> tuple[str | None, float | None]:
    stop_hit = float(bar["bid_low"]) <= stop
    target_hit = float(bar["bid_high"]) >= target
    if stop_hit:
        return "stop_loss", stop
    if target_hit:
        return "take_profit", target
    return None, None


def price_hit_for_short(bar: pd.Series, stop: float, target: float) -> tuple[str | None, float | None]:
    stop_hit = float(bar["ask_high"]) >= stop
    target_hit = float(bar["ask_low"]) <= target
    if stop_hit:
        return "stop_loss", stop
    if target_hit:
        return "take_profit", target
    return None, None


def main() -> None:
    args = parse_args()

    pip_size = load_pip_size()
    bars = pd.read_parquet(args.bars_file)
    if bars.empty:
        raise ValueError("Bars dataset is empty")
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)
    latest_bar = bars.iloc[-1]
    latest_bar_ts = latest_bar["timestamp"]

    signals_dir = Path(args.signals_dir)
    state_dir = Path(args.state_dir)
    log_dir = Path(args.log_dir)
    ensure_paper_trading_layout(infer_layout_root(signals_dir, state_dir, log_dir))
    signals_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    open_path = state_dir / "open_positions.csv"
    closed_path = state_dir / "closed_positions.csv"
    equity_path = state_dir / "equity_curve.csv"
    execution_log_path = log_dir / "execution_log.csv"
    if not execution_log_path.exists():
        pd.DataFrame(columns=EXECUTION_LOG_COLS).to_csv(execution_log_path, index=False)

    open_df = read_csv_or_empty(open_path, OPEN_COLS)
    closed_df = read_csv_or_empty(closed_path, CLOSED_COLS)
    equity_df = read_csv_or_empty(equity_path, EQUITY_COLS)
    execution_events: list[dict] = []

    # Step 1: monitor existing open trades against the latest bar.
    closed_rows: list[dict] = []
    remaining_rows: list[dict] = []

    for _, row in open_df.iterrows():
        side = str(row["side"])
        stop = float(row["stop_price"])
        target = float(row["target_price"])
        entry = float(row["entry_price"])

        if side == "long":
            exit_reason, exit_price = price_hit_for_long(latest_bar, stop, target)
        else:
            exit_reason, exit_price = price_hit_for_short(latest_bar, stop, target)

        if exit_reason is None or exit_price is None:
            remaining_rows.append(row.to_dict())
            continue

        pnl = (exit_price - entry) if side == "long" else (entry - exit_price)
        pnl_pips = pnl / pip_size

        closed_rows.append(
            {
                "entry_time": row["timestamp"],
                "exit_time": latest_bar_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "symbol": row["symbol"],
                "strategy": row["strategy"],
                "side": side,
                "entry_price": entry,
                "exit_price": float(exit_price),
                "pnl_pips": float(pnl_pips),
                "pnl": float(pnl),
                "exit_reason": exit_reason,
            }
        )
        execution_events.append(
            {
                "timestamp": latest_bar_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "event": "trade_closed_target" if exit_reason == "take_profit" else "trade_closed_stop",
                "strategy": str(row["strategy"]),
                "symbol": str(row["symbol"]),
                "message": f"side={side} pnl_pips={pnl_pips:.2f}",
            }
        )

        print(f"Trade closed: {'TP hit' if exit_reason == 'take_profit' else 'SL hit'}")
        sign = "+" if pnl_pips >= 0 else ""
        print(f"PnL: {sign}{pnl_pips:.1f} pips")

    updated_open_df = pd.DataFrame(remaining_rows, columns=OPEN_COLS)

    # Step 2: open a trade from the latest signal file if it is a real signal and not already tracked.
    signal_file = latest_signal_file(signals_dir)
    opened_new = False
    if signal_file is not None:
        signal = load_signal(signal_file)
        if signal.get("signal") != "none":
            execution_events.append(
                {
                    "timestamp": str(signal["timestamp"]),
                    "event": "signal_consumed",
                    "strategy": str(signal.get("strategy", "")),
                    "symbol": str(signal.get("symbol", "")),
                    "message": signal_file.name,
                }
            )
            signal_ts = str(signal["timestamp"])
            signal_key = (
                signal_ts,
                str(signal["symbol"]),
                str(signal["side"]),
                float(signal["entry_price"]),
            )

            existing_open_keys = {
                (str(r["timestamp"]), str(r["symbol"]), str(r["side"]), float(r["entry_price"]))
                for _, r in updated_open_df.iterrows()
            }
            existing_closed_keys = {
                (str(r["entry_time"]), str(r["symbol"]), str(r["side"]), float(r["entry_price"]))
                for _, r in closed_df.iterrows()
            }

            if signal_key not in existing_open_keys and signal_key not in existing_closed_keys:
                open_row = {
                    "timestamp": signal_ts,
                    "symbol": str(signal["symbol"]),
                    "strategy": str(signal["strategy"]),
                    "side": str(signal["side"]),
                    "entry_price": float(signal["entry_price"]),
                    "stop_price": float(signal["stop_price"]),
                    "target_price": float(signal["target_price"]),
                }
                updated_open_df = pd.concat(
                    [updated_open_df, pd.DataFrame([open_row], columns=OPEN_COLS)],
                    ignore_index=True,
                )
                opened_new = True
                execution_events.append(
                    {
                        "timestamp": signal_ts,
                        "event": "trade_opened",
                        "strategy": open_row["strategy"],
                        "symbol": open_row["symbol"],
                        "message": f"side={open_row['side']} entry={open_row['entry_price']}",
                    }
                )

                print(
                    f"Open trade: {'BUY' if open_row['side'] == 'long' else 'SELL'} "
                    f"{open_row['symbol']} {open_row['entry_price']:.4f}"
                )
                print(f"Stop: {open_row['stop_price']:.4f}")
                print(f"Target: {open_row['target_price']:.4f}")

    # Step 3: persist open/closed trades.
    write_csv(updated_open_df, open_path, OPEN_COLS)

    if closed_rows:
        new_closed_df = pd.DataFrame(closed_rows, columns=CLOSED_COLS)
        closed_df = pd.concat([closed_df, new_closed_df], ignore_index=True)
        closed_df = closed_df.sort_values(["exit_time", "entry_time"]).reset_index(drop=True)
    write_csv(closed_df, closed_path, CLOSED_COLS)

    # Step 4: update equity curve from newly closed trades.
    if closed_rows:
        running_equity = 0.0 if equity_df.empty else float(equity_df["equity"].iloc[-1])
        equity_rows = []
        for row in closed_rows:
            running_equity += float(row["pnl"])
            equity_rows.append({"timestamp": row["exit_time"], "equity": running_equity})
        equity_df = pd.concat([equity_df, pd.DataFrame(equity_rows, columns=EQUITY_COLS)], ignore_index=True)
    write_csv(equity_df, equity_path, EQUITY_COLS)
    append_execution_log(execution_log_path, execution_events)

    if not opened_new and not closed_rows:
        print(latest_bar_ts.tz_convert("UTC").strftime("%Y-%m-%d %H:%M UTC"))
        print("no trade events")


if __name__ == "__main__":
    main()
