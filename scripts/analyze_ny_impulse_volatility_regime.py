from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze NY impulse strategy performance by volatility regime"
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
        default="outputs/ny_impulse_volatility_regime",
        help="Output directory",
    )
    return parser.parse_args()


def compute_daily_atr(bars: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date

    daily = (
        df.groupby("date")
        .agg(
            daily_high=("mid_high", "max"),
            daily_low=("mid_low", "min"),
            daily_close=("mid_close", "last"),
        )
        .reset_index()
        .sort_values("date")
        .reset_index(drop=True)
    )

    daily["prev_close"] = daily["daily_close"].shift(1)
    daily["tr"] = np.where(
        daily["prev_close"].isna(),
        daily["daily_high"] - daily["daily_low"],
        np.maximum.reduce(
            [
                (daily["daily_high"] - daily["daily_low"]).to_numpy(),
                (daily["daily_high"] - daily["prev_close"]).abs().to_numpy(),
                (daily["daily_low"] - daily["prev_close"]).abs().to_numpy(),
            ]
        ),
    )
    daily["daily_atr"] = daily["tr"].rolling(window=period, min_periods=1).mean()
    return daily


def assign_volatility_regimes(daily_atr: pd.Series) -> tuple[pd.Series, dict[str, float]]:
    p30 = float(daily_atr.quantile(0.30))
    p70 = float(daily_atr.quantile(0.70))

    def _label(value: float) -> str:
        if value <= p30:
            return "low_vol"
        if value <= p70:
            return "mid_vol"
        return "high_vol"

    regimes = daily_atr.map(_label)
    return regimes, {"p30": p30, "p70": p70}


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


def compute_regime_metrics(trades_with_regime: pd.DataFrame) -> list[dict[str, float | int | str]]:
    output: list[dict[str, float | int | str]] = []
    for regime in ("low_vol", "mid_vol", "high_vol"):
        subset = trades_with_regime[trades_with_regime["volatility_regime"] == regime].copy()
        subset = subset.sort_values("exit_time")
        net = subset["net_pnl"] if not subset.empty else pd.Series(dtype=float)
        gross = subset["gross_pnl"] if "gross_pnl" in subset.columns else net

        avg_win = float(net[net > 0].mean()) if (net > 0).any() else 0.0
        avg_loss = float(net[net < 0].mean()) if (net < 0).any() else 0.0
        row = {
            "regime": regime,
            "trade_count": int(len(subset)),
            "win_rate": float((net > 0).mean()) if len(subset) else 0.0,
            "gross_pnl": float(gross.sum()) if len(subset) else 0.0,
            "net_pnl": float(net.sum()) if len(subset) else 0.0,
            "profit_factor": profit_factor(net) if len(subset) else 0.0,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "max_drawdown": max_drawdown(net) if len(subset) else 0.0,
        }
        output.append(row)
    return output


def print_table(metrics: list[dict[str, float | int | str]]) -> None:
    print("regime | trades | win_rate | PF | net_pnl | max_dd")
    for row in metrics:
        print(
            f"{row['regime']:<8} | "
            f"{int(row['trade_count']):>6} | "
            f"{float(row['win_rate']):>8.4f} | "
            f"{float(row['profit_factor']):>6.4f} | "
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

    daily = compute_daily_atr(bars)
    regimes, thresholds = assign_volatility_regimes(daily["daily_atr"])
    daily["volatility_regime"] = regimes

    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)
    trades["trade_date"] = trades["entry_time"].dt.date

    trades_with_regime = trades.merge(
        daily[["date", "daily_atr", "volatility_regime"]],
        left_on="trade_date",
        right_on="date",
        how="left",
    ).drop(columns=["date"])

    if trades_with_regime["volatility_regime"].isna().any():
        missing = int(trades_with_regime["volatility_regime"].isna().sum())
        raise RuntimeError(f"Failed to map regime for {missing} trades")

    metrics = compute_regime_metrics(trades_with_regime)
    summary = {
        "bars_file": args.bars,
        "trades_file": args.trades,
        "atr_period": 14,
        "thresholds": thresholds,
        "days_analyzed": int(len(daily)),
        "trades_analyzed": int(len(trades_with_regime)),
        "regime_metrics": metrics,
    }

    summary_path = output_dir / "volatility_regime_summary.json"
    trades_path = output_dir / "volatility_regime_trades.csv"
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
        "daily_atr",
        "volatility_regime",
    ]
    available_cols = [c for c in export_cols if c in trades_with_regime.columns]
    trades_with_regime[available_cols].to_csv(trades_path, index=False)

    print_table(metrics)
    print(f"\nSaved summary: {summary_path}")
    print(f"Saved trades by regime: {trades_path}")


if __name__ == "__main__":
    main()
