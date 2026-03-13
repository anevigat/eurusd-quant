from __future__ import annotations

from typing import Any

import pandas as pd

from eurusd_quant.analytics.metrics import compute_metrics


TRADE_TIME_COLUMNS = ("signal_time", "entry_time", "exit_time")


def normalize_trades(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    for column in TRADE_TIME_COLUMNS:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column], utc=True)
    return out


def compute_yearly_metrics(trades: pd.DataFrame, *, time_column: str = "entry_time") -> pd.DataFrame:
    normalized = normalize_trades(trades)
    if normalized.empty:
        return pd.DataFrame(
            columns=[
                "year",
                "total_trades",
                "win_rate",
                "gross_pnl",
                "net_pnl",
                "expectancy",
                "profit_factor",
                "max_drawdown",
            ]
        )

    if time_column not in normalized.columns:
        raise ValueError(f"Trades dataframe is missing required time column '{time_column}'")

    normalized = normalized.copy()
    normalized["year"] = normalized[time_column].dt.year
    rows: list[dict[str, Any]] = []
    for year, year_trades in normalized.groupby("year", sort=True):
        metrics = compute_metrics(year_trades)
        rows.append({"year": int(year), **metrics})
    return pd.DataFrame(rows)


def compute_dominant_year_pnl_share(yearly_metrics: pd.DataFrame) -> float:
    if yearly_metrics.empty or "net_pnl" not in yearly_metrics.columns:
        return 0.0

    positive_pnl = yearly_metrics.loc[yearly_metrics["net_pnl"] > 0, "net_pnl"]
    total_positive_pnl = float(positive_pnl.sum())
    if total_positive_pnl <= 0.0:
        return 0.0
    return float(float(positive_pnl.max()) / total_positive_pnl)


def compute_daily_equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    normalized = normalize_trades(trades)
    if normalized.empty:
        return pd.DataFrame(columns=["date", "day_pnl", "equity", "rolling_peak", "drawdown"])

    if "exit_time" not in normalized.columns:
        raise ValueError("Trades dataframe is missing required time column 'exit_time'")

    daily = (
        normalized.assign(date=normalized["exit_time"].dt.normalize())
        .groupby("date", as_index=False)
        .agg(day_pnl=("net_pnl", "sum"))
        .sort_values("date")
        .reset_index(drop=True)
    )
    daily["equity"] = daily["day_pnl"].cumsum()
    daily["rolling_peak"] = daily["equity"].cummax()
    daily["drawdown"] = daily["equity"] - daily["rolling_peak"]
    return daily


def build_validation_summary(trades: pd.DataFrame) -> dict[str, Any]:
    normalized = normalize_trades(trades)
    metrics = compute_metrics(normalized)
    yearly_metrics = compute_yearly_metrics(normalized)

    start_time = None
    end_time = None
    if not normalized.empty and "entry_time" in normalized.columns and "exit_time" in normalized.columns:
        start_time = normalized["entry_time"].min()
        end_time = normalized["exit_time"].max()

    return {
        **metrics,
        "years_covered": int(yearly_metrics["year"].nunique()) if not yearly_metrics.empty else 0,
        "dominant_year_pnl_share": compute_dominant_year_pnl_share(yearly_metrics),
        "start_time": start_time.isoformat() if start_time is not None else None,
        "end_time": end_time.isoformat() if end_time is not None else None,
    }
