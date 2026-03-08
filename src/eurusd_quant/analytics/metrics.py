from __future__ import annotations

import numpy as np
import pandas as pd


def compute_metrics(trades_df: pd.DataFrame) -> dict:
    if trades_df.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "gross_pnl": 0.0,
            "net_pnl": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
        }

    gross_pnl = float(trades_df["gross_pnl"].sum())
    net_pnl = float(trades_df["net_pnl"].sum())
    total_trades = int(len(trades_df))

    wins = trades_df[trades_df["net_pnl"] > 0]["net_pnl"]
    losses = trades_df[trades_df["net_pnl"] < 0]["net_pnl"]

    win_rate = float(len(wins) / total_trades) if total_trades else 0.0
    average_win = float(wins.mean()) if not wins.empty else 0.0
    average_loss = float(losses.mean()) if not losses.empty else 0.0
    expectancy = float(trades_df["net_pnl"].mean()) if total_trades else 0.0

    loss_sum_abs = abs(float(losses.sum()))
    if loss_sum_abs == 0.0:
        profit_factor = float(np.inf) if not wins.empty else 0.0
    else:
        profit_factor = float(float(wins.sum()) / loss_sum_abs)

    equity_curve = trades_df["net_pnl"].cumsum()
    rolling_peak = equity_curve.cummax()
    drawdown = equity_curve - rolling_peak
    max_drawdown = float(abs(drawdown.min()))

    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "average_win": average_win,
        "average_loss": average_loss,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
    }
