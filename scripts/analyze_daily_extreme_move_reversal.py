from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.data.loaders import load_bars


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze daily extreme move reversal behavior on EURUSD."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/daily_extreme_move_reversal_diagnostic",
        help="Directory for summary.json, daily_metrics.csv, distribution.csv",
    )
    parser.add_argument(
        "--threshold-atr",
        type=float,
        default=1.0,
        help="Extreme move threshold in ATR units",
    )
    return parser.parse_args()


def _safe_q(series: pd.Series, q: float) -> float:
    clean = series.dropna()
    if clean.empty:
        return 0.0
    return float(clean.quantile(q))


def build_daily_bars(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date.astype(str)

    daily = (
        df.groupby("date", as_index=False)
        .agg(
            daily_open=("mid_open", "first"),
            daily_high=("mid_high", "max"),
            daily_low=("mid_low", "min"),
            daily_close=("mid_close", "last"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )

    daily["daily_return"] = daily["daily_close"] - daily["daily_open"]
    daily["prev_close"] = daily["daily_close"].shift(1)
    tr = pd.concat(
        [
            daily["daily_high"] - daily["daily_low"],
            (daily["daily_high"] - daily["prev_close"]).abs(),
            (daily["daily_low"] - daily["prev_close"]).abs(),
        ],
        axis=1,
    ).max(axis=1)
    daily["daily_atr"] = tr.rolling(window=14, min_periods=1).mean()
    return daily


def compute_daily_metrics(bars: pd.DataFrame, threshold_atr: float) -> pd.DataFrame:
    daily = build_daily_bars(bars)
    daily["daily_return_atr"] = (daily["daily_return"].abs() / daily["daily_atr"]).replace([float("inf")], pd.NA)
    daily["strong_momentum_flag"] = daily["daily_return_atr"] >= threshold_atr
    daily["direction"] = daily["daily_return"].apply(lambda x: "up" if x > 0 else ("down" if x < 0 else "flat"))

    daily["next_close"] = daily["daily_close"].shift(-1)
    daily["next_move"] = daily["next_close"] - daily["daily_close"]

    direction_sign = daily["daily_return"].apply(lambda x: 1.0 if x > 0 else (-1.0 if x < 0 else 0.0))
    daily["continuation_1d"] = direction_sign * daily["next_move"]
    daily["reversal_1d"] = -daily["continuation_1d"]

    daily["continuation_1d_atr"] = daily["continuation_1d"] / daily["daily_atr"]
    daily["reversal_1d_atr"] = daily["reversal_1d"] / daily["daily_atr"]

    out_cols = [
        "date",
        "daily_open",
        "daily_high",
        "daily_low",
        "daily_close",
        "daily_return",
        "daily_atr",
        "daily_return_atr",
        "strong_momentum_flag",
        "direction",
        "continuation_1d",
        "reversal_1d",
        "continuation_1d_atr",
        "reversal_1d_atr",
    ]
    return daily[out_cols].copy()


def build_distribution(daily: pd.DataFrame) -> pd.DataFrame:
    strong = daily[daily["strong_momentum_flag"]]
    rows: list[dict[str, object]] = []
    for metric in ["daily_return_atr", "reversal_1d_atr", "continuation_1d_atr"]:
        s = strong[metric]
        for label, q in [("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]:
            rows.append({"metric": metric, "stat": label, "value": _safe_q(s, q)})
    return pd.DataFrame(rows)


def build_summary(daily: pd.DataFrame, dataset_path: str, threshold_atr: float) -> dict[str, object]:
    days = len(daily)
    strong = daily[daily["strong_momentum_flag"]].copy()
    strong = strong.dropna(subset=["continuation_1d_atr", "reversal_1d_atr"])  # requires next day

    reversal_prob = float((strong["reversal_1d"] > 0).mean()) if not strong.empty else 0.0
    continuation_prob = float((strong["continuation_1d"] > 0).mean()) if not strong.empty else 0.0

    return {
        "dataset": dataset_path,
        "threshold_atr": threshold_atr,
        "days_analyzed": int(days),
        "strong_momentum_frequency": float(daily["strong_momentum_flag"].mean()) if days else 0.0,
        "bullish_momentum_frequency": float((daily["direction"] == "up").mean()) if days else 0.0,
        "bearish_momentum_frequency": float((daily["direction"] == "down").mean()) if days else 0.0,
        "strong_events": int(len(strong)),
        "reversal_probability_1d": reversal_prob,
        "continuation_probability_1d": continuation_prob,
        "median_reversal_1d_atr": _safe_q(strong["reversal_1d_atr"], 0.50),
        "median_continuation_1d_atr": _safe_q(strong["continuation_1d_atr"], 0.50),
        "p75_reversal_1d_atr": _safe_q(strong["reversal_1d_atr"], 0.75),
        "p75_continuation_1d_atr": _safe_q(strong["continuation_1d_atr"], 0.75),
    }


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(args.bars)
    daily = compute_daily_metrics(bars, threshold_atr=args.threshold_atr)
    distribution = build_distribution(daily)
    summary = build_summary(daily, dataset_path=args.bars, threshold_atr=args.threshold_atr)

    daily_path = out_dir / "daily_metrics.csv"
    dist_path = out_dir / "distribution.csv"
    summary_path = out_dir / "summary.json"

    daily.to_csv(daily_path, index=False)
    distribution.to_csv(dist_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"strong_momentum_frequency: {summary['strong_momentum_frequency']:.4f}")
    print(f"reversal_probability_1d: {summary['reversal_probability_1d']:.4f}")
    print(f"continuation_probability_1d: {summary['continuation_probability_1d']:.4f}")
    print(f"median_reversal_1d_atr: {summary['median_reversal_1d_atr']:.4f}")
    print(f"median_continuation_1d_atr: {summary['median_continuation_1d_atr']:.4f}")

    print(f"\nSaved daily metrics: {daily_path}")
    print(f"Saved distribution: {dist_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
