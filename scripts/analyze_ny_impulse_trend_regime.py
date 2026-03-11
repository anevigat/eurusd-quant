from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze NY impulse strategy performance by daily trend regime"
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
        default="outputs/ny_impulse_trend_regime",
        help="Output directory",
    )
    return parser.parse_args()


def compute_daily_trend_strength(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.time

    open_rows = df[df["time"] == pd.Timestamp("00:00").time()][["date", "mid_open"]].rename(
        columns={"mid_open": "open_00_00_exact"}
    )
    close_rows = df[df["time"] == pd.Timestamp("23:45").time()][["date", "mid_close"]].rename(
        columns={"mid_close": "close_23_45_exact"}
    )
    fallback = (
        df.groupby("date")
        .agg(day_open=("mid_open", "first"), day_close=("mid_close", "last"))
        .reset_index()
    )
    daily = fallback.merge(open_rows, on="date", how="left").merge(close_rows, on="date", how="left")
    daily["open_00_00"] = daily["open_00_00_exact"].fillna(daily["day_open"])
    daily["close_23_45"] = daily["close_23_45_exact"].fillna(daily["day_close"])
    daily = daily.sort_values("date").reset_index(drop=True)
    daily["trend_strength"] = (daily["close_23_45"] - daily["open_00_00"]).abs()
    return daily[["date", "open_00_00", "close_23_45", "trend_strength"]]


def assign_trend_regimes(trend_strength: pd.Series) -> tuple[pd.Series, dict[str, float]]:
    p30 = float(trend_strength.quantile(0.30))
    p70 = float(trend_strength.quantile(0.70))

    def _label(value: float) -> str:
        if value <= p30:
            return "range_day"
        if value <= p70:
            return "normal_day"
        return "trend_day"

    return trend_strength.map(_label), {"p30": p30, "p70": p70}


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
    for regime in ("range_day", "normal_day", "trend_day"):
        subset = trades_with_regime[trades_with_regime["trend_regime"] == regime].sort_values("exit_time")
        net = subset["net_pnl"] if not subset.empty else pd.Series(dtype=float)
        gross = subset["gross_pnl"] if "gross_pnl" in subset.columns else net

        metrics.append(
            {
                "regime": regime,
                "trade_count": int(len(subset)),
                "win_rate": float((net > 0).mean()) if len(subset) else 0.0,
                "gross_pnl": float(gross.sum()) if len(subset) else 0.0,
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
            f"{row['regime']:<10} | "
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

    daily = compute_daily_trend_strength(bars)
    regimes, thresholds = assign_trend_regimes(daily["trend_strength"])
    daily["trend_regime"] = regimes

    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)
    trades["trade_date"] = trades["entry_time"].dt.date

    trades_with_regime = trades.merge(
        daily[["date", "open_00_00", "close_23_45", "trend_strength", "trend_regime"]],
        left_on="trade_date",
        right_on="date",
        how="left",
    ).drop(columns=["date"])

    if trades_with_regime["trend_regime"].isna().any():
        missing = int(trades_with_regime["trend_regime"].isna().sum())
        raise RuntimeError(f"Failed to map trend regime for {missing} trades")

    metrics = compute_regime_metrics(trades_with_regime)
    summary = {
        "bars_file": args.bars,
        "trades_file": args.trades,
        "thresholds": thresholds,
        "days_analyzed": int(len(daily)),
        "trades_analyzed": int(len(trades_with_regime)),
        "regime_metrics": metrics,
    }

    summary_path = output_dir / "trend_regime_summary.json"
    trades_path = output_dir / "trend_regime_trades.csv"
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
        "open_00_00",
        "close_23_45",
        "trend_strength",
        "trend_regime",
    ]
    available_cols = [c for c in export_cols if c in trades_with_regime.columns]
    trades_with_regime[available_cols].to_csv(trades_path, index=False)

    print_table(metrics)
    print(f"\nSaved summary: {summary_path}")
    print(f"Saved trades by regime: {trades_path}")


if __name__ == "__main__":
    main()
