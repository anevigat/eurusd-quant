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

from eurusd_quant.analytics.metrics import compute_metrics
from eurusd_quant.data.loaders import load_bars
from eurusd_quant.execution.simulator import ExecutionConfig, ExecutionSimulator
from eurusd_quant.strategies.ny_impulse_mean_reversion import (
    NYImpulseMeanReversionConfig,
    NYImpulseMeanReversionStrategy,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnostics and robustness checks for ny_impulse_mean_reversion."
    )
    parser.add_argument(
        "--trades",
        default="outputs/ny_impulse_mean_reversion_smoke/trades.parquet",
        help="Path to strategy trades parquet",
    )
    parser.add_argument(
        "--metrics",
        default="outputs/ny_impulse_mean_reversion_smoke/metrics.json",
        help="Path to baseline metrics json",
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Path to bars parquet used for analysis and stress re-run",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/ny_impulse_mean_reversion_diagnostics",
        help="Diagnostics output directory",
    )
    parser.add_argument(
        "--stress-spread-penalty-pips",
        type=float,
        default=0.0,
        help="Optional extra fee penalty in pips per trade during stress re-run",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def profit_factor(pnl: pd.Series) -> float:
    win_sum = float(pnl[pnl > 0].sum())
    loss_abs = abs(float(pnl[pnl < 0].sum()))
    if loss_abs == 0.0:
        return float(np.inf) if win_sum > 0 else 0.0
    return float(win_sum / loss_abs)


def win_rate(pnl: pd.Series) -> float:
    if len(pnl) == 0:
        return 0.0
    return float((pnl > 0).mean())


def normalize_trades(trades: pd.DataFrame, pip_size: float) -> pd.DataFrame:
    out = trades.copy()
    for col in ("signal_time", "entry_time", "exit_time"):
        out[col] = pd.to_datetime(out[col], utc=True)
    if "pnl_pips" not in out.columns:
        out["pnl_pips"] = out["net_pnl"] / pip_size
    out["year"] = out["entry_time"].dt.year
    out["year_month"] = out["entry_time"].dt.strftime("%Y-%m")
    out["weekday"] = out["entry_time"].dt.day_name()
    out["entry_date"] = out["entry_time"].dt.date.astype(str)
    return out


def build_trade_distribution(trades: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    yearly = (
        trades.groupby("year")
        .agg(
            trade_count=("year", "size"),
            win_rate=("net_pnl", lambda s: float((s > 0).mean()) if len(s) else 0.0),
            net_pnl=("net_pnl", "sum"),
            expectancy=("net_pnl", "mean"),
            profit_factor=("net_pnl", lambda s: profit_factor(s)),
        )
        .reset_index()
        .sort_values("year")
    )
    distribution = {
        "total_trades": int(len(trades)),
        "trades_per_year": {
            str(int(k)): int(v) for k, v in trades.groupby("year").size().sort_index().items()
        },
        "trades_per_month": {
            str(k): int(v) for k, v in trades.groupby("year_month").size().sort_index().items()
        },
        "trades_per_weekday": {
            str(k): int(v)
            for k, v in trades.groupby("weekday").size().reindex(
                ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                fill_value=0,
            ).items()
        },
    }
    return distribution, yearly


def build_exit_reason_counts(trades: pd.DataFrame) -> dict[str, int]:
    labels = ["stop_loss", "take_profit", "time_exit", "flatten_intraday", "end_of_data"]
    counts = {label: int((trades["exit_reason"] == label).sum()) for label in labels}
    extras = sorted(set(trades["exit_reason"]) - set(labels))
    for label in extras:
        counts[str(label)] = int((trades["exit_reason"] == label).sum())
    return counts


def build_win_loss_stats(trades: pd.DataFrame) -> dict[str, float]:
    wins = trades.loc[trades["pnl_pips"] > 0, "pnl_pips"]
    losses = trades.loc[trades["pnl_pips"] < 0, "pnl_pips"]
    avg_win = float(wins.mean()) if not wins.empty else 0.0
    avg_loss = float(losses.mean()) if not losses.empty else 0.0
    median_win = float(wins.median()) if not wins.empty else 0.0
    median_loss = float(losses.median()) if not losses.empty else 0.0
    wl_ratio = float(abs(avg_win / avg_loss)) if avg_loss != 0 else float(np.inf)
    return {
        "win_rate": win_rate(trades["net_pnl"]),
        "average_win_pips": avg_win,
        "average_loss_pips": avg_loss,
        "median_win_pips": median_win,
        "median_loss_pips": median_loss,
        "win_loss_ratio": wl_ratio,
    }


def build_side_stats(trades: pd.DataFrame) -> dict[str, dict]:
    side_stats: dict[str, dict] = {}
    for side in ("long", "short"):
        side_df = trades[trades["side"] == side]
        pnl = side_df["net_pnl"]
        side_stats[side] = {
            "trade_count": int(len(side_df)),
            "win_rate": win_rate(pnl),
            "net_pnl": float(pnl.sum()) if len(side_df) else 0.0,
            "expectancy": float(pnl.mean()) if len(side_df) else 0.0,
            "profit_factor": profit_factor(pnl) if len(side_df) else 0.0,
        }
    return side_stats


def compute_ny_impulse_sizes(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time
    impulse_mask = (df["tod"] >= pd.Timestamp("13:00").time()) & (
        df["tod"] < pd.Timestamp("13:30").time()
    )
    impulse = df.loc[impulse_mask, ["date", "mid_high", "mid_low"]]
    daily = (
        impulse.groupby("date")
        .agg(impulse_high=("mid_high", "max"), impulse_low=("mid_low", "min"))
        .reset_index()
    )
    daily["impulse_size"] = daily["impulse_high"] - daily["impulse_low"]
    return daily[["date", "impulse_size"]]


def build_impulse_bucket_stats(trades: pd.DataFrame, impulse_sizes: pd.DataFrame) -> dict:
    merged = trades.merge(impulse_sizes, left_on="entry_date", right_on="date", how="left")
    merged = merged.drop(columns=["date"])
    valid = merged[merged["impulse_size"].notna()].copy()
    if valid.empty:
        return {"thresholds": {}, "buckets": {}}

    thresholds = {
        "p50": float(impulse_sizes["impulse_size"].quantile(0.50)),
        "p75": float(impulse_sizes["impulse_size"].quantile(0.75)),
        "p90": float(impulse_sizes["impulse_size"].quantile(0.90)),
    }
    buckets: dict[str, dict] = {}
    for label, threshold in thresholds.items():
        subset = valid[valid["impulse_size"] >= threshold]
        pnl = subset["net_pnl"]
        buckets[label] = {
            "trade_count": int(len(subset)),
            "win_rate": win_rate(pnl),
            "net_pnl": float(pnl.sum()) if len(subset) else 0.0,
            "profit_factor": profit_factor(pnl) if len(subset) else 0.0,
        }
    return {"thresholds": thresholds, "buckets": buckets}


def compute_excursions(trades: pd.DataFrame, bars: pd.DataFrame, pip_size: float) -> dict[str, float]:
    rows: list[tuple[float, float]] = []
    for _, trade in trades.iterrows():
        segment = bars[
            (bars["timestamp"] >= trade["entry_time"]) & (bars["timestamp"] <= trade["exit_time"])
        ]
        if segment.empty:
            continue
        entry_price = float(trade["entry_price"])
        if trade["side"] == "long":
            mfe = (float(segment["bid_high"].max()) - entry_price) / pip_size
            mae = (entry_price - float(segment["bid_low"].min())) / pip_size
        else:
            mfe = (entry_price - float(segment["ask_low"].min())) / pip_size
            mae = (float(segment["ask_high"].max()) - entry_price) / pip_size
        rows.append((float(mfe), float(mae)))

    if not rows:
        raise RuntimeError("No MFE/MAE rows computed from trades/bars overlap")

    mfe_vals = np.array([x[0] for x in rows], dtype=float)
    mae_vals = np.array([x[1] for x in rows], dtype=float)
    median_mfe = float(np.median(mfe_vals))
    median_mae = float(np.median(mae_vals))
    return {
        "trades_analyzed": int(len(rows)),
        "median_mfe": median_mfe,
        "median_mae": median_mae,
        "mean_mfe": float(np.mean(mfe_vals)),
        "mean_mae": float(np.mean(mae_vals)),
        "p95_mfe": float(np.percentile(mfe_vals, 95)),
        "p95_mae": float(np.percentile(mae_vals, 95)),
        "mfe_mae_ratio": float(median_mfe / abs(median_mae)) if median_mae != 0 else float(np.inf),
    }


def run_stress_backtest(
    bars: pd.DataFrame,
    execution_cfg: dict,
    strategy_cfg: dict,
    spread_penalty_pips: float,
) -> dict:
    pip_size = float(execution_cfg["pip_size"])
    stress_cfg = dict(execution_cfg)
    stress_cfg["market_slippage_pips"] = float(execution_cfg["market_slippage_pips"]) * 2.0
    stress_cfg["stop_slippage_pips"] = float(execution_cfg["stop_slippage_pips"]) * 2.0
    stress_cfg["fee_per_trade"] = float(execution_cfg["fee_per_trade"]) + (spread_penalty_pips * pip_size)

    strategy = NYImpulseMeanReversionStrategy(NYImpulseMeanReversionConfig.from_dict(strategy_cfg))
    simulator = ExecutionSimulator(ExecutionConfig.from_dict(stress_cfg))

    for _, bar in bars.iterrows():
        simulator.process_bar(bar)
        order = strategy.generate_order(
            bar,
            has_open_position=simulator.has_open_position(),
            has_pending_order=simulator.has_pending_order(),
        )
        if order is not None:
            simulator.submit_order(order)
    if not bars.empty:
        simulator.close_open_position_at_end(bars.iloc[-1])

    stress_trades = simulator.get_trades_df()
    stress_metrics = compute_metrics(stress_trades)
    stress_metrics["stress_spread_penalty_pips"] = spread_penalty_pips
    return stress_metrics


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_metrics = load_json(Path(args.metrics))
    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    strategy_cfg = dict(strategy_cfg_all["ny_impulse_mean_reversion"])
    pip_size = float(execution_cfg["pip_size"])

    trades = pd.read_parquet(args.trades)
    bars = load_bars(args.bars)
    bars_subset = bars[["timestamp", "mid_high", "mid_low", "bid_high", "bid_low", "ask_high", "ask_low"]].copy()
    bars_subset["timestamp"] = pd.to_datetime(bars_subset["timestamp"], utc=True)
    bars_subset = bars_subset.sort_values("timestamp").reset_index(drop=True)

    trades = normalize_trades(trades, pip_size=pip_size)
    if trades.empty:
        raise ValueError("Trades input is empty")

    trade_distribution, yearly_stats = build_trade_distribution(trades)
    exit_reason_counts = build_exit_reason_counts(trades)
    win_loss_stats = build_win_loss_stats(trades)
    side_stats = build_side_stats(trades)
    impulse_sizes = compute_ny_impulse_sizes(bars)
    impulse_bucket_stats = build_impulse_bucket_stats(trades, impulse_sizes)
    excursions = compute_excursions(trades, bars_subset, pip_size=pip_size)
    stress_metrics = run_stress_backtest(
        bars=bars,
        execution_cfg=execution_cfg,
        strategy_cfg=strategy_cfg,
        spread_penalty_pips=args.stress_spread_penalty_pips,
    )

    (out_dir / "trade_distribution.json").write_text(
        json.dumps(trade_distribution, indent=2), encoding="utf-8"
    )
    (out_dir / "exit_reason_counts.json").write_text(
        json.dumps(exit_reason_counts, indent=2), encoding="utf-8"
    )
    (out_dir / "win_loss_stats.json").write_text(
        json.dumps(win_loss_stats, indent=2), encoding="utf-8"
    )
    (out_dir / "side_stats.json").write_text(json.dumps(side_stats, indent=2), encoding="utf-8")
    (out_dir / "impulse_bucket_stats.json").write_text(
        json.dumps(impulse_bucket_stats, indent=2), encoding="utf-8"
    )
    (out_dir / "excursions.json").write_text(json.dumps(excursions, indent=2), encoding="utf-8")
    yearly_stats.to_csv(out_dir / "yearly_stats.csv", index=False)
    (out_dir / "stress_metrics.json").write_text(
        json.dumps(stress_metrics, indent=2), encoding="utf-8"
    )

    best_year_row = yearly_stats.sort_values("net_pnl", ascending=False).iloc[0]
    worst_year_row = yearly_stats.sort_values("net_pnl", ascending=True).iloc[0]
    buckets = impulse_bucket_stats.get("buckets", {})
    best_bucket = None
    if buckets:
        best_bucket = max(buckets.items(), key=lambda kv: kv[1]["net_pnl"])[0]

    summary = {
        "baseline_metrics": baseline_metrics,
        "trade_distribution": trade_distribution,
        "exit_reason_counts": exit_reason_counts,
        "win_loss_stats": win_loss_stats,
        "side_stats": side_stats,
        "impulse_bucket_stats": impulse_bucket_stats,
        "excursions": excursions,
        "best_year": int(best_year_row["year"]),
        "worst_year": int(worst_year_row["year"]),
        "best_impulse_bucket": best_bucket,
        "stress_metrics": stress_metrics,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("NY impulse mean reversion diagnostics complete")
    print(f"total_trades: {trade_distribution['total_trades']}")
    print(f"profit_factor: {baseline_metrics.get('profit_factor', 0.0):.4f}")
    print(f"win_rate: {win_loss_stats['win_rate']:.4f}")
    print(f"average_win_pips: {win_loss_stats['average_win_pips']:.4f}")
    print(f"average_loss_pips: {win_loss_stats['average_loss_pips']:.4f}")
    print(f"mfe_mae_ratio: {excursions['mfe_mae_ratio']:.4f}")
    print(f"best_year: {int(best_year_row['year'])}")
    print(f"worst_year: {int(worst_year_row['year'])}")
    print(f"best_impulse_bucket: {best_bucket}")
    print(f"stress_test_pf: {stress_metrics['profit_factor']:.4f}")
    print(f"outputs_dir: {out_dir}")


if __name__ == "__main__":
    main()
