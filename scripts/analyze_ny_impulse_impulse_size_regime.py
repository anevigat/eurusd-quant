from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


IMPULSE_START = pd.Timestamp("13:00").time()
IMPULSE_END = pd.Timestamp("13:30").time()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze NY impulse strategy performance by impulse-size regime"
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Bars parquet path",
    )
    parser.add_argument(
        "--trades",
        default="outputs/ny_impulse_exit_models_extended/atr_1_0/trades.parquet",
        help="Trades parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/ny_impulse_impulse_regime",
        help="Output directory",
    )
    return parser.parse_args()


def compute_daily_impulse_size(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.time

    window = df[(df["time"] >= IMPULSE_START) & (df["time"] < IMPULSE_END)].copy()
    # Keep impulse sizing aligned with strategy threshold logic: high-low in impulse window.
    daily = (
        window.groupby("date")
        .agg(
            impulse_high=("mid_high", "max"),
            impulse_low=("mid_low", "min"),
        )
        .reset_index()
        .sort_values("date")
        .reset_index(drop=True)
    )
    daily["impulse_size"] = (daily["impulse_high"] - daily["impulse_low"]).abs()
    return daily


def assign_impulse_regimes(
    impulse_size: pd.Series,
) -> tuple[pd.Series, dict[str, float]]:
    p50 = float(impulse_size.quantile(0.50))
    p75 = float(impulse_size.quantile(0.75))
    p90 = float(impulse_size.quantile(0.90))

    def _label(value: float) -> str:
        if value <= p50:
            return "small_impulse"
        if value <= p75:
            return "medium_impulse"
        if value <= p90:
            return "large_impulse"
        return "extreme_impulse"

    return impulse_size.map(_label), {"p50": p50, "p75": p75, "p90": p90}


def profit_factor(pnl: pd.Series) -> float:
    win_sum = float(pnl[pnl > 0].sum())
    loss_abs = abs(float(pnl[pnl < 0].sum()))
    if loss_abs == 0.0:
        return float("inf") if win_sum > 0 else 0.0
    return float(win_sum / loss_abs)


def max_drawdown(pnl: pd.Series) -> float:
    if pnl.empty:
        return 0.0
    equity = pnl.cumsum()
    drawdown = equity.cummax() - equity
    return float(drawdown.max())


def compute_regime_metrics(
    trades_with_regime: pd.DataFrame,
) -> list[dict[str, float | int | str]]:
    metrics: list[dict[str, float | int | str]] = []
    for regime in ("small_impulse", "medium_impulse", "large_impulse", "extreme_impulse"):
        subset = trades_with_regime[trades_with_regime["impulse_regime"] == regime].sort_values("exit_time")
        net = subset["net_pnl"] if not subset.empty else pd.Series(dtype=float)

        metrics.append(
            {
                "regime": regime,
                "trade_count": int(len(subset)),
                "win_rate": float((net > 0).mean()) if len(subset) else 0.0,
                "net_pnl": float(net.sum()) if len(subset) else 0.0,
                "profit_factor": profit_factor(net) if len(subset) else 0.0,
                "average_win": float(net[net > 0].mean()) if (net > 0).any() else 0.0,
                "average_loss": float(net[net < 0].mean()) if (net < 0).any() else 0.0,
                "max_drawdown": max_drawdown(net) if len(subset) else 0.0,
            }
        )
    return metrics


def print_table(metrics: list[dict[str, float | int | str]]) -> None:
    print("regime | trades | win_rate | PF | net_pnl | max_dd")
    for row in metrics:
        print(
            f"{row['regime']:<15} | "
            f"{int(row['trade_count']):>6} | "
            f"{float(row['win_rate']):>8.4f} | "
            f"{float(row['profit_factor']):>7.4f} | "
            f"{float(row['net_pnl']):>8.6f} | "
            f"{float(row['max_drawdown']):>8.6f}"
        )


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bars = pd.read_parquet(args.bars)
    trades = pd.read_parquet(args.trades)
    if bars.empty:
        raise ValueError("Bars input is empty")
    if trades.empty:
        raise ValueError("Trades input is empty")

    daily = compute_daily_impulse_size(bars)
    regimes, thresholds = assign_impulse_regimes(daily["impulse_size"])
    daily["impulse_regime"] = regimes

    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)
    trades["trade_date"] = trades["entry_time"].dt.date

    trades_with_regime = trades.merge(
        daily[["date", "impulse_high", "impulse_low", "impulse_size", "impulse_regime"]],
        left_on="trade_date",
        right_on="date",
        how="left",
    ).drop(columns=["date"])

    if trades_with_regime["impulse_regime"].isna().any():
        missing = int(trades_with_regime["impulse_regime"].isna().sum())
        raise RuntimeError(f"Failed to map impulse regime for {missing} trades")

    metrics = compute_regime_metrics(trades_with_regime)
    summary = {
        "bars_file": args.bars,
        "trades_file": args.trades,
        "impulse_window_utc": {
            "start": IMPULSE_START.strftime("%H:%M"),
            "end_exclusive": IMPULSE_END.strftime("%H:%M"),
        },
        "thresholds": thresholds,
        "days_analyzed": int(len(daily)),
        "trades_analyzed": int(len(trades_with_regime)),
        "regime_metrics": metrics,
    }

    summary_path = output_dir / "impulse_regime_summary.json"
    trades_path = output_dir / "impulse_regime_trades.csv"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    export_cols = [
        "signal_time",
        "entry_time",
        "exit_time",
        "symbol",
        "side",
        "entry_price",
        "exit_price",
        "gross_pnl",
        "net_pnl",
        "impulse_high",
        "impulse_low",
        "impulse_size",
        "impulse_regime",
    ]
    available_cols = [c for c in export_cols if c in trades_with_regime.columns]
    trades_with_regime[available_cols].to_csv(trades_path, index=False)

    print_table(metrics)
    print(f"\nSaved summary: {summary_path}")
    print(f"Saved trades by regime: {trades_path}")


if __name__ == "__main__":
    main()
