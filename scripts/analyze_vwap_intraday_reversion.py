from __future__ import annotations

import argparse
import json
import sys
from datetime import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.data.loaders import load_bars


ACTIVE_START = time(7, 0)
ACTIVE_END = time(17, 0)
ATR_PERIOD = 14


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze intraday VWAP proxy deviation and mean reversion on EURUSD M15."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/vwap_intraday_reversion_diagnostic",
        help="Output directory for summary/distribution/daily metrics",
    )
    return parser.parse_args()


def _window_mask(series: pd.Series, start: time, end: time) -> pd.Series:
    if start <= end:
        return (series >= start) & (series < end)
    return (series >= start) | (series < end)


def compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    prev_close = df["mid_close"].shift(1)
    tr = pd.concat(
        [
            (df["mid_high"] - df["mid_low"]).abs(),
            (df["mid_high"] - prev_close).abs(),
            (df["mid_low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1, skipna=True)
    return tr.rolling(period, min_periods=period).mean()


def compute_intraday_vwap_proxy(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["mid_high"] + df["mid_low"] + df["mid_close"]) / 3.0
    if "volume" in df.columns:
        # If real volume appears in future datasets, use standard cumulative VWAP.
        weighted = typical_price * df["volume"]
        cum_weighted = weighted.groupby(df["date"]).cumsum()
        cum_volume = df["volume"].groupby(df["date"]).cumsum()
        return cum_weighted / cum_volume
    # FX proxy: cumulative average of typical price from 00:00 each day.
    return typical_price.groupby(df["date"]).expanding().mean().reset_index(level=0, drop=True)


def compute_reversion_ratio(deviation_now: float, deviation_at_horizon: float) -> float:
    abs_now = abs(float(deviation_now))
    if abs_now == 0.0:
        return 0.0
    return (abs_now - abs(float(deviation_at_horizon))) / abs_now


def assign_deviation_buckets(
    abs_deviation_atr: pd.Series,
) -> tuple[pd.Series, dict[str, float]]:
    p50 = float(abs_deviation_atr.quantile(0.50))
    p75 = float(abs_deviation_atr.quantile(0.75))
    p90 = float(abs_deviation_atr.quantile(0.90))

    def _bucket(value: float) -> str:
        if value <= p50:
            return "small_dev"
        if value <= p75:
            return "medium_dev"
        if value <= p90:
            return "large_dev"
        return "extreme_dev"

    return abs_deviation_atr.map(_bucket), {"p50": p50, "p75": p75, "p90": p90}


def build_observations(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time
    df["atr"] = compute_atr(df, period=ATR_PERIOD)
    df["intraday_vwap"] = compute_intraday_vwap_proxy(df)
    df["deviation"] = df["mid_close"] - df["intraday_vwap"]
    df["deviation_atr"] = df["deviation"] / df["atr"]
    df["abs_deviation_atr"] = df["deviation_atr"].abs()

    rows: list[dict[str, float | str | int]] = []
    for _, day_df in df.groupby("date", sort=True):
        day_df = day_df.reset_index(drop=True)
        active_mask = _window_mask(day_df["tod"], ACTIVE_START, ACTIVE_END)
        active_idx = day_df.index[active_mask].tolist()
        for i in active_idx:
            row = day_df.iloc[i]
            if pd.isna(row["atr"]) or pd.isna(row["deviation_atr"]):
                continue
            if float(row["abs_deviation_atr"]) == 0.0:
                continue

            rev4 = float("nan")
            rev8 = float("nan")
            if i + 4 < len(day_df):
                rev4 = compute_reversion_ratio(
                    float(row["deviation"]), float(day_df.iloc[i + 4]["deviation"])
                )
            if i + 8 < len(day_df):
                rev8 = compute_reversion_ratio(
                    float(row["deviation"]), float(day_df.iloc[i + 8]["deviation"])
                )

            rows.append(
                {
                    "timestamp": row["timestamp"].isoformat(),
                    "date": row["date"],
                    "deviation": float(row["deviation"]),
                    "deviation_atr": float(row["deviation_atr"]),
                    "abs_deviation_atr": float(row["abs_deviation_atr"]),
                    "reversion_ratio_4bars": rev4,
                    "reversion_ratio_8bars": rev8,
                }
            )

    observations = pd.DataFrame(rows)
    if observations.empty:
        raise ValueError("No eligible active-window observations were produced.")

    buckets, thresholds = assign_deviation_buckets(observations["abs_deviation_atr"])
    observations["deviation_bucket"] = buckets
    observations.attrs["bucket_thresholds"] = thresholds
    return observations


def _safe_quantile(series: pd.Series, q: float) -> float:
    clean = series.dropna()
    if clean.empty:
        return 0.0
    return float(clean.quantile(q))


def _bucket_stats(obs: pd.DataFrame, bucket: str) -> dict[str, float | int | str]:
    subset = obs[obs["deviation_bucket"] == bucket]
    return {
        "bucket": bucket,
        "count": int(len(subset)),
        "median_reversion_ratio_4bars": _safe_quantile(subset["reversion_ratio_4bars"], 0.50),
        "p75_reversion_ratio_4bars": _safe_quantile(subset["reversion_ratio_4bars"], 0.75),
        "median_reversion_ratio_8bars": _safe_quantile(subset["reversion_ratio_8bars"], 0.50),
        "p75_reversion_ratio_8bars": _safe_quantile(subset["reversion_ratio_8bars"], 0.75),
    }


def _side_stats(obs: pd.DataFrame, positive: bool) -> dict[str, float | int | str]:
    side = "positive" if positive else "negative"
    subset = obs[obs["deviation"] > 0] if positive else obs[obs["deviation"] < 0]
    return {
        "side": side,
        "count": int(len(subset)),
        "median_reversion_ratio_4bars": _safe_quantile(subset["reversion_ratio_4bars"], 0.50),
        "p75_reversion_ratio_4bars": _safe_quantile(subset["reversion_ratio_4bars"], 0.75),
        "median_reversion_ratio_8bars": _safe_quantile(subset["reversion_ratio_8bars"], 0.50),
        "p75_reversion_ratio_8bars": _safe_quantile(subset["reversion_ratio_8bars"], 0.75),
    }


def classify_diagnostic(summary: dict[str, object]) -> tuple[str, bool]:
    bucket = {
        row["bucket"]: row
        for row in summary["bucket_stats"]  # type: ignore[index]
    }
    large = bucket["large_dev"]
    extreme = bucket["extreme_dev"]

    bars_analyzed = int(summary["bars_analyzed"])
    meaningful_count = int(large["count"]) + int(extreme["count"])
    meaningful_freq = meaningful_count / bars_analyzed if bars_analyzed else 0.0

    promising = (
        meaningful_freq >= 0.10
        and float(large["median_reversion_ratio_4bars"]) > 0.05
        and float(extreme["median_reversion_ratio_4bars"]) > float(
            bucket["medium_dev"]["median_reversion_ratio_4bars"]
        )
    )
    verdict = (
        "promising_enough_to_implement_mvp"
        if promising
        else "researched_but_not_promising"
    )
    return verdict, promising


def build_summary(obs: pd.DataFrame, dataset_path: str) -> dict[str, object]:
    thresholds = obs.attrs.get("bucket_thresholds", {})
    summary: dict[str, object] = {
        "dataset": dataset_path,
        "active_window_utc": {"start": "07:00", "end_exclusive": "17:00"},
        "vwap_method": (
            "cumulative typical-price average from 00:00 per day (volume-free FX proxy)"
        ),
        "atr_period": ATR_PERIOD,
        "bars_analyzed": int(len(obs)),
        "deviation_bucket_thresholds_abs_atr": thresholds,
        "median_abs_deviation_atr": _safe_quantile(obs["abs_deviation_atr"], 0.50),
        "p75_abs_deviation_atr": _safe_quantile(obs["abs_deviation_atr"], 0.75),
        "p90_abs_deviation_atr": _safe_quantile(obs["abs_deviation_atr"], 0.90),
        "bucket_stats": [
            _bucket_stats(obs, "small_dev"),
            _bucket_stats(obs, "medium_dev"),
            _bucket_stats(obs, "large_dev"),
            _bucket_stats(obs, "extreme_dev"),
        ],
        "positive_deviation_stats": _side_stats(obs, positive=True),
        "negative_deviation_stats": _side_stats(obs, positive=False),
    }
    verdict, promising = classify_diagnostic(summary)
    summary["diagnostic_verdict"] = verdict
    summary["promising_enough_for_mvp"] = promising
    return summary


def build_distribution_table(obs: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for stat in ("min", "p10", "p25", "p50", "p75", "p90", "p95", "max"):
        if stat == "min":
            value = float(obs["abs_deviation_atr"].min())
        elif stat == "max":
            value = float(obs["abs_deviation_atr"].max())
        else:
            q = float(stat[1:]) / 100.0
            value = float(obs["abs_deviation_atr"].quantile(q))
        rows.append(
            {
                "section": "abs_deviation_atr_distribution",
                "key": stat,
                "value": value,
            }
        )

    for bucket in ("small_dev", "medium_dev", "large_dev", "extreme_dev"):
        subset = obs[obs["deviation_bucket"] == bucket]
        rows.append(
            {
                "section": "bucket_count",
                "key": bucket,
                "value": int(len(subset)),
            }
        )
        rows.append(
            {
                "section": "bucket_median_reversion_4bars",
                "key": bucket,
                "value": _safe_quantile(subset["reversion_ratio_4bars"], 0.50),
            }
        )
        rows.append(
            {
                "section": "bucket_median_reversion_8bars",
                "key": bucket,
                "value": _safe_quantile(subset["reversion_ratio_8bars"], 0.50),
            }
        )

    return pd.DataFrame(rows)


def write_outputs(
    output_dir: Path, summary: dict[str, object], obs: pd.DataFrame, distribution: pd.DataFrame
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    export_cols = [
        "timestamp",
        "deviation",
        "deviation_atr",
        "deviation_bucket",
        "reversion_ratio_4bars",
        "reversion_ratio_8bars",
    ]
    obs[export_cols].to_csv(output_dir / "daily_metrics.csv", index=False)
    distribution.to_csv(output_dir / "distribution.csv", index=False)


def main() -> None:
    args = parse_args()
    bars = load_bars(args.bars)
    obs = build_observations(bars)
    summary = build_summary(obs, dataset_path=args.bars)
    distribution = build_distribution_table(obs)
    output_dir = Path(args.output_dir)
    write_outputs(output_dir, summary, obs, distribution)

    print(f"bars_analyzed: {summary['bars_analyzed']}")
    print(f"median_abs_deviation_atr: {summary['median_abs_deviation_atr']:.4f}")
    print(f"p75_abs_deviation_atr: {summary['p75_abs_deviation_atr']:.4f}")
    print(f"p90_abs_deviation_atr: {summary['p90_abs_deviation_atr']:.4f}")
    print(f"diagnostic_verdict: {summary['diagnostic_verdict']}")
    print(f"\nSaved outputs in: {output_dir}")


if __name__ == "__main__":
    main()
