from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze strategy behavior from trades and bars")
    parser.add_argument("--trades", required=True, help="Path to trades parquet")
    parser.add_argument("--bars", required=True, help="Path to bars parquet")
    parser.add_argument(
        "--output-dir",
        default="outputs/false_breakout_reversal_diagnostics",
        help="Output directory for diagnostics",
    )
    parser.add_argument("--pip-size", type=float, default=None, help="Optional pip size override")
    return parser.parse_args()


def load_pip_size(override: float | None) -> float:
    if override is not None:
        return float(override)
    with (ROOT / "config" / "execution.yaml").open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return float(cfg["pip_size"])


def profit_factor(pnl: pd.Series) -> float:
    wins = pnl[pnl > 0].sum()
    losses = pnl[pnl < 0].sum()
    loss_abs = abs(float(losses))
    if loss_abs == 0.0:
        return float(np.inf) if wins > 0 else 0.0
    return float(float(wins) / loss_abs)


def win_rate(pnl: pd.Series) -> float:
    if len(pnl) == 0:
        return 0.0
    return float((pnl > 0).mean())


def excursion_for_trade(trade: pd.Series, bars: pd.DataFrame, pip_size: float) -> tuple[float, float] | None:
    entry_time = trade["entry_time"]
    exit_time = trade["exit_time"]
    entry_price = float(trade["entry_price"])
    side = trade["side"]

    segment = bars[(bars["timestamp"] >= entry_time) & (bars["timestamp"] <= exit_time)]
    if segment.empty:
        return None

    if side == "long":
        mfe = (float(segment["bid_high"].max()) - entry_price) / pip_size
        mae = (entry_price - float(segment["bid_low"].min())) / pip_size
    elif side == "short":
        mfe = (entry_price - float(segment["ask_low"].min())) / pip_size
        mae = (float(segment["ask_high"].max()) - entry_price) / pip_size
    else:
        return None
    return float(mfe), float(mae)


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pip_size = load_pip_size(args.pip_size)

    trades = pd.read_parquet(args.trades).copy()
    bars = pd.read_parquet(
        args.bars, columns=["timestamp", "bid_high", "bid_low", "ask_high", "ask_low"]
    ).copy()

    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)

    if trades.empty:
        raise ValueError("Trades file is empty; cannot analyze behavior")

    for col in ["signal_time", "entry_time", "exit_time"]:
        trades[col] = pd.to_datetime(trades[col], utc=True)

    if "pnl_pips" not in trades.columns:
        trades["pnl_pips"] = trades["net_pnl"] / pip_size

    trades["entry_month"] = trades["entry_time"].dt.strftime("%Y-%m")
    trades["entry_weekday"] = trades["entry_time"].dt.day_name()
    trades["entry_hour"] = trades["entry_time"].dt.hour

    trade_distribution = {
        "total_trades": int(len(trades)),
        "trades_per_month": {
            str(k): int(v) for k, v in trades.groupby("entry_month").size().sort_index().items()
        },
        "trades_per_weekday": {
            str(k): int(v)
            for k, v in trades.groupby("entry_weekday").size().reindex(
                ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                fill_value=0,
            ).items()
        },
        "trades_by_entry_hour": {
            str(int(k)): int(v) for k, v in trades.groupby("entry_hour").size().sort_index().items()
        },
    }
    (output_dir / "trade_distribution.json").write_text(
        json.dumps(trade_distribution, indent=2), encoding="utf-8"
    )

    exit_labels = ["stop_loss", "take_profit", "time_exit", "flatten_intraday", "end_of_data"]
    exit_reason_counts = {label: int((trades["exit_reason"] == label).sum()) for label in exit_labels}
    extra_reasons = sorted(set(trades["exit_reason"]) - set(exit_labels))
    for label in extra_reasons:
        exit_reason_counts[str(label)] = int((trades["exit_reason"] == label).sum())
    (output_dir / "exit_reason_counts.json").write_text(
        json.dumps(exit_reason_counts, indent=2), encoding="utf-8"
    )

    wins = trades[trades["pnl_pips"] > 0]["pnl_pips"]
    losses = trades[trades["pnl_pips"] < 0]["pnl_pips"]
    avg_win = float(wins.mean()) if not wins.empty else 0.0
    avg_loss = float(losses.mean()) if not losses.empty else 0.0
    median_win = float(wins.median()) if not wins.empty else 0.0
    median_loss = float(losses.median()) if not losses.empty else 0.0
    wl_ratio = float(abs(avg_win / avg_loss)) if avg_loss != 0 else float(np.inf)
    win_loss_stats = {
        "win_rate": win_rate(trades["net_pnl"]),
        "average_win_pips": avg_win,
        "average_loss_pips": avg_loss,
        "median_win_pips": median_win,
        "median_loss_pips": median_loss,
        "win_loss_ratio": wl_ratio,
    }
    (output_dir / "win_loss_stats.json").write_text(
        json.dumps(win_loss_stats, indent=2), encoding="utf-8"
    )

    side_stats: dict[str, dict[str, float | int]] = {}
    for side in ["long", "short"]:
        side_df = trades[trades["side"] == side]
        pnl = side_df["net_pnl"]
        side_stats[side] = {
            "trade_count": int(len(side_df)),
            "win_rate": win_rate(pnl),
            "net_pnl": float(pnl.sum()) if len(side_df) else 0.0,
            "expectancy": float(pnl.mean()) if len(side_df) else 0.0,
            "profit_factor": profit_factor(pnl) if len(side_df) else 0.0,
        }
    (output_dir / "side_stats.json").write_text(json.dumps(side_stats, indent=2), encoding="utf-8")

    hourly_df = (
        trades.groupby("entry_hour")
        .agg(
            trade_count=("entry_hour", "size"),
            win_rate=("net_pnl", lambda s: float((s > 0).mean()) if len(s) else 0.0),
            net_pnl=("net_pnl", "sum"),
            average_pnl=("net_pnl", "mean"),
        )
        .reset_index()
        .sort_values("entry_hour")
    )
    hourly_df.to_csv(output_dir / "hourly_stats.csv", index=False)

    excursions: list[tuple[float, float]] = []
    for _, trade in trades.iterrows():
        ex = excursion_for_trade(trade, bars, pip_size=pip_size)
        if ex is not None:
            excursions.append(ex)

    if not excursions:
        raise RuntimeError("No MFE/MAE values computed from the provided trades and bars")
    mfe_vals = np.array([x[0] for x in excursions], dtype=float)
    mae_vals = np.array([x[1] for x in excursions], dtype=float)
    median_mfe = float(np.median(mfe_vals))
    median_mae = float(np.median(mae_vals))
    excursions_summary = {
        "trades_analyzed": int(len(excursions)),
        "median_mfe": median_mfe,
        "median_mae": median_mae,
        "mean_mfe": float(np.mean(mfe_vals)),
        "mean_mae": float(np.mean(mae_vals)),
        "p95_mfe": float(np.percentile(mfe_vals, 95)),
        "p95_mae": float(np.percentile(mae_vals, 95)),
        "mfe_mae_ratio": float(median_mfe / abs(median_mae)) if median_mae != 0 else float(np.inf),
    }
    (output_dir / "excursions.json").write_text(
        json.dumps(excursions_summary, indent=2), encoding="utf-8"
    )

    holding_distribution = {
        str(int(k)): int(v)
        for k, v in trades.groupby("bars_held").size().sort_index().items()
    }
    holding_summary = {
        "average_holding_bars": float(trades["bars_held"].mean()),
        "median_holding_bars": float(trades["bars_held"].median()),
        "holding_bars_distribution": holding_distribution,
    }
    (output_dir / "holding_time.json").write_text(
        json.dumps(holding_summary, indent=2), encoding="utf-8"
    )

    overall_pf = profit_factor(trades["net_pnl"])
    best_hour = int(hourly_df.sort_values("net_pnl", ascending=False).iloc[0]["entry_hour"])
    worst_hour = int(hourly_df.sort_values("net_pnl", ascending=True).iloc[0]["entry_hour"])

    print("Strategy behavior diagnostics complete")
    print(f"trade_count: {len(trades)}")
    print(f"win_rate: {win_loss_stats['win_rate']:.4f}")
    print(f"profit_factor: {overall_pf:.4f}")
    print(f"average_win_pips: {win_loss_stats['average_win_pips']:.4f}")
    print(f"average_loss_pips: {win_loss_stats['average_loss_pips']:.4f}")
    print(f"exit_reason_breakdown: {json.dumps(exit_reason_counts, sort_keys=True)}")
    print(f"mfe_mae_ratio: {excursions_summary['mfe_mae_ratio']:.4f}")
    print(f"most_profitable_entry_hour: {best_hour}")
    print(f"worst_entry_hour: {worst_hour}")
    print(f"outputs_dir: {output_dir}")


if __name__ == "__main__":
    main()
