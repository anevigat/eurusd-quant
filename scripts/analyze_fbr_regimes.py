from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze regime dependence of frozen false_breakout_reversal trades."
    )
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument(
        "--trades-root",
        default="outputs/experiments/false_breakout_reversal_atr_target_0809",
        help="Root directory that contains yearly trades parquet outputs",
    )
    parser.add_argument(
        "--bars-dir",
        default="data/bars/15m",
        help="Directory containing yearly bars parquet files",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/diagnostics/fbr_regime_analysis",
        help="Output directory for regime diagnostics artifacts",
    )
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--quantiles", type=int, default=5)
    return parser.parse_args()


def profit_factor(pnl: pd.Series) -> float:
    win_sum = float(pnl[pnl > 0].sum())
    loss_sum_abs = abs(float(pnl[pnl < 0].sum()))
    if loss_sum_abs == 0.0:
        return float(np.inf) if win_sum > 0 else 0.0
    return float(win_sum / loss_sum_abs)


def summarize_segment(df: pd.DataFrame) -> dict[str, float]:
    pnl = df["net_pnl"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    return {
        "trade_count": int(len(df)),
        "win_rate": float((pnl > 0).mean()) if len(df) else 0.0,
        "profit_factor": profit_factor(pnl) if len(df) else 0.0,
        "expectancy": float(pnl.mean()) if len(df) else 0.0,
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "net_pnl": float(pnl.sum()) if len(df) else 0.0,
    }


def compute_atr(bars: pd.DataFrame, period: int) -> pd.Series:
    prev_close = bars["mid_close"].shift(1)
    high_low = bars["mid_high"] - bars["mid_low"]
    high_prev = (bars["mid_high"] - prev_close).abs()
    low_prev = (bars["mid_low"] - prev_close).abs()
    tr = np.maximum.reduce([high_low.to_numpy(), high_prev.to_numpy(), low_prev.to_numpy()])
    tr = pd.Series(tr, index=bars.index)
    return tr.rolling(window=period, min_periods=period).mean()


def add_daily_context_features(bars: pd.DataFrame) -> pd.DataFrame:
    bars = bars.copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)
    bars["trade_date"] = bars["timestamp"].dt.date
    bars["tod"] = bars["timestamp"].dt.time

    asian_mask = (bars["tod"] >= pd.Timestamp("00:00").time()) & (
        bars["tod"] < pd.Timestamp("06:00").time()
    )
    asian = (
        bars.loc[asian_mask]
        .groupby("trade_date")
        .agg(asian_high=("mid_high", "max"), asian_low=("mid_low", "min"))
        .reset_index()
    )
    asian["asian_range_size"] = asian["asian_high"] - asian["asian_low"]
    asian["asian_midpoint"] = (asian["asian_high"] + asian["asian_low"]) / 2.0

    pre_london_mask = (bars["tod"] >= pd.Timestamp("06:00").time()) & (
        bars["tod"] < pd.Timestamp("08:00").time()
    )
    pre_london_rows = bars.loc[pre_london_mask].copy()
    if pre_london_rows.empty:
        pre_london = pd.DataFrame(
            columns=["trade_date", "pre_london_first", "pre_london_last", "pre_london_trend"]
        )
    else:
        pre_london = (
            pre_london_rows.groupby("trade_date")
            .agg(pre_london_first=("mid_open", "first"), pre_london_last=("mid_close", "last"))
            .reset_index()
        )
        pre_london["pre_london_trend"] = (
            pre_london["pre_london_last"] - pre_london["pre_london_first"]
        )

    daily_features = asian.merge(pre_london, on="trade_date", how="left")
    return daily_features


def add_entry_features(
    trades: pd.DataFrame,
    bars: pd.DataFrame,
    daily_features: pd.DataFrame,
    atr_period: int,
) -> pd.DataFrame:
    bars = bars.copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)
    bars["atr_at_entry"] = compute_atr(bars, period=atr_period)
    bars["spread_at_entry"] = bars["spread_open"]
    entry_lookup = bars[["timestamp", "atr_at_entry", "spread_at_entry"]]

    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"], utc=True)
    out["entry_date"] = out["entry_time"].dt.date
    out["entry_year"] = out["entry_time"].dt.year
    out["month"] = out["entry_time"].dt.month
    out["year_month"] = out["entry_time"].dt.strftime("%Y-%m")
    out["day_of_week"] = out["entry_time"].dt.day_name()

    out = out.merge(entry_lookup, left_on="entry_time", right_on="timestamp", how="left").drop(
        columns=["timestamp"]
    )
    out = out.merge(daily_features, left_on="entry_date", right_on="trade_date", how="left").drop(
        columns=["trade_date"]
    )

    out["distance_from_asian_midpoint"] = out["entry_price"] - out["asian_midpoint"]
    out["distance_from_asian_midpoint_abs"] = out["distance_from_asian_midpoint"].abs()

    out["pre_london_trend_direction"] = np.where(
        out["pre_london_trend"] > 0,
        "up",
        np.where(out["pre_london_trend"] < 0, "down", "flat"),
    )
    return out


def add_quantile_labels(df: pd.DataFrame, quantiles: int) -> pd.DataFrame:
    out = df.copy()
    quantile_specs = [
        ("asian_range_size", "asian_range_quantile"),
        ("atr_at_entry", "volatility_quantile"),
        ("spread_at_entry", "spread_quantile"),
        ("distance_from_asian_midpoint_abs", "distance_midpoint_quantile"),
    ]
    for col, out_col in quantile_specs:
        valid = out[col].notna()
        if valid.sum() < quantiles:
            out[out_col] = pd.NA
            continue
        binned = pd.qcut(out.loc[valid, col], q=quantiles, duplicates="drop")
        codes = binned.cat.codes
        out.loc[valid, out_col] = codes.map(lambda c: f"Q{int(c) + 1}" if c >= 0 else pd.NA)
    return out


def summarize_by_feature(df: pd.DataFrame, feature: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped = df.dropna(subset=[feature]).groupby(feature)
    for segment, segment_df in grouped:
        metrics = summarize_segment(segment_df)
        rows.append({"feature": feature, "segment": str(segment), **metrics})
    return pd.DataFrame(rows)


def build_feature_distributions(df: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = [
        "asian_range_size",
        "atr_at_entry",
        "spread_at_entry",
        "distance_from_asian_midpoint_abs",
        "pre_london_trend",
    ]
    rows: list[dict[str, Any]] = []
    for col in numeric_cols:
        series = df[col].dropna()
        if series.empty:
            continue
        rows.append(
            {
                "feature": col,
                "count": int(series.size),
                "mean": float(series.mean()),
                "std": float(series.std()),
                "min": float(series.min()),
                "p25": float(series.quantile(0.25)),
                "p50": float(series.quantile(0.50)),
                "p75": float(series.quantile(0.75)),
                "max": float(series.max()),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    if args.end_year < args.start_year:
        raise ValueError("--end-year must be >= --start-year")

    years = list(range(args.start_year, args.end_year + 1))
    trades_root = Path(args.trades_root)
    bars_dir = Path(args.bars_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_trades_with_features: list[pd.DataFrame] = []
    loaded_years: list[int] = []

    for year in years:
        trades_path = trades_root / str(year) / "trades.parquet"
        bars_path = bars_dir / f"eurusd_bars_15m_{year}.parquet"
        if not trades_path.exists():
            raise FileNotFoundError(f"Missing trades file: {trades_path}")
        if not bars_path.exists():
            raise FileNotFoundError(f"Missing bars file: {bars_path}")

        trades = pd.read_parquet(trades_path).copy()
        bars = pd.read_parquet(
            bars_path,
            columns=[
                "timestamp",
                "mid_open",
                "mid_high",
                "mid_low",
                "mid_close",
                "spread_open",
            ],
        ).copy()

        daily_features = add_daily_context_features(bars)
        trades_with_features = add_entry_features(
            trades=trades,
            bars=bars,
            daily_features=daily_features,
            atr_period=args.atr_period,
        )
        trades_with_features["year"] = year
        all_trades_with_features.append(trades_with_features)
        loaded_years.append(year)
        print(f"Loaded {year}: trades={len(trades_with_features)}")

    combined = pd.concat(all_trades_with_features, ignore_index=True)
    combined = add_quantile_labels(combined, quantiles=args.quantiles)

    feature_summaries = []
    for feature in ["day_of_week", "month", "side", "pre_london_trend_direction"]:
        feature_summaries.append(summarize_by_feature(combined, feature=feature))
    regime_summary_by_feature = pd.concat(feature_summaries, ignore_index=True)

    quantile_summaries = []
    for feature in [
        "asian_range_quantile",
        "volatility_quantile",
        "spread_quantile",
        "distance_midpoint_quantile",
    ]:
        quantile_summaries.append(summarize_by_feature(combined, feature=feature))
    regime_summary_by_quantile = pd.concat(quantile_summaries, ignore_index=True)

    monthly_rows = []
    for year_month, group in combined.groupby("year_month"):
        monthly_rows.append({"year_month": year_month, **summarize_segment(group)})
    monthly_performance = pd.DataFrame(monthly_rows).sort_values("year_month").reset_index(drop=True)

    yearly_rows = []
    for year, group in combined.groupby("year"):
        yearly_rows.append({"year": int(year), **summarize_segment(group)})
    yearly_performance = pd.DataFrame(yearly_rows).sort_values("year").reset_index(drop=True)

    distributions = build_feature_distributions(combined)

    regime_summary_by_feature.to_csv(output_dir / "regime_summary_by_feature.csv", index=False)
    regime_summary_by_quantile.to_csv(output_dir / "regime_summary_by_quantile.csv", index=False)
    monthly_performance.to_csv(output_dir / "monthly_performance.csv", index=False)
    yearly_performance.to_csv(output_dir / "yearly_performance.csv", index=False)
    distributions.to_csv(output_dir / "feature_distributions.csv", index=False)

    summary = {
        "years_requested": years,
        "years_loaded": loaded_years,
        "total_trades_loaded": int(len(combined)),
        "output_dir": str(output_dir),
    }
    (output_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Print concise pattern hints directly from computed segment tables.
    for feature in ["asian_range_quantile", "volatility_quantile", "spread_quantile"]:
        subset = regime_summary_by_quantile[regime_summary_by_quantile["feature"] == feature]
        if subset.empty:
            continue
        best = subset.sort_values("net_pnl", ascending=False).iloc[0]
        worst = subset.sort_values("net_pnl", ascending=True).iloc[0]
        print(
            f"{feature}: best={best['segment']} (net_pnl={best['net_pnl']:.6f}) "
            f"worst={worst['segment']} (net_pnl={worst['net_pnl']:.6f})"
        )

    print(f"Loaded years: {loaded_years}")
    print(f"Total trades loaded: {len(combined)}")
    print(f"Wrote diagnostics to: {output_dir}")


if __name__ == "__main__":
    main()
