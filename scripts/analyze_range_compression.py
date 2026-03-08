from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Asian range compression vs London volatility expansion")
    parser.add_argument("--bars", required=True, help="Path to 15m EURUSD bars parquet")
    parser.add_argument("--output-dir", default="outputs/range_compression", help="Directory for outputs")
    parser.add_argument("--pip-size", type=float, default=None, help="Optional pip-size override")
    return parser.parse_args()


def load_pip_size(explicit: float | None) -> float:
    if explicit is not None:
        return explicit
    with (ROOT / "config" / "execution.yaml").open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return float(cfg["pip_size"])


def compute_daily_ranges(bars: pd.DataFrame, pip_size: float) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp")
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["time"] = df["timestamp"].dt.time

    asian_mask = (df["time"] >= pd.Timestamp("00:00:00").time()) & (df["time"] < pd.Timestamp("06:00:00").time())
    london_mask = (df["time"] >= pd.Timestamp("07:00:00").time()) & (df["time"] < pd.Timestamp("12:00:00").time())

    asian = (
        df[asian_mask]
        .groupby("date")
        .agg(asian_high=("mid_high", "max"), asian_low=("mid_low", "min"))
        .assign(asian_range_pips=lambda x: (x["asian_high"] - x["asian_low"]) / pip_size)
    )
    london = (
        df[london_mask]
        .groupby("date")
        .agg(london_high=("mid_high", "max"), london_low=("mid_low", "min"))
        .assign(london_move_pips=lambda x: (x["london_high"] - x["london_low"]) / pip_size)
    )

    merged = asian[["asian_range_pips"]].join(london[["london_move_pips"]], how="inner").reset_index()
    return merged.sort_values("date").reset_index(drop=True)


def add_expanding_percentile(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    percentiles: list[float] = []
    series = out["asian_range_pips"]
    for idx, value in enumerate(series):
        hist = series.iloc[: idx + 1]
        pct = float((hist <= value).mean() * 100.0)
        percentiles.append(pct)
    out["range_percentile"] = percentiles
    return out


def build_bucket_stats(df: pd.DataFrame) -> pd.DataFrame:
    edges = list(range(0, 101, 10))
    labels = [f"{i}-{i + 10}%" for i in range(0, 100, 10)]
    work = df.copy()
    work["percentile_bucket"] = pd.cut(
        work["range_percentile"],
        bins=edges,
        labels=labels,
        include_lowest=True,
        right=True,
    )
    grouped = (
        work.groupby("percentile_bucket", observed=False)
        .agg(
            count_days=("date", "count"),
            median_asian_range=("asian_range_pips", "median"),
            median_london_move=("london_move_pips", "median"),
            mean_london_move=("london_move_pips", "mean"),
            p75_london_move=("london_move_pips", lambda s: s.quantile(0.75)),
            p90_london_move=("london_move_pips", lambda s: s.quantile(0.90)),
        )
        .reindex(labels)
        .reset_index()
    )
    return grouped


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pip_size = load_pip_size(args.pip_size)
    bars = pd.read_parquet(args.bars, columns=["timestamp", "mid_high", "mid_low"])
    daily = compute_daily_ranges(bars, pip_size=pip_size)
    if daily.empty:
        raise ValueError("No overlapping Asian/London session days found")

    daily = add_expanding_percentile(daily)
    daily.to_csv(out_dir / "daily_ranges.csv", index=False)
    bucket_stats = build_bucket_stats(daily)
    bucket_path = out_dir / "range_stats.csv"
    bucket_stats.to_csv(bucket_path, index=False)

    corr = float(daily["asian_range_pips"].corr(daily["london_move_pips"]))

    low_bucket = bucket_stats[bucket_stats["percentile_bucket"] == "0-10%"]["median_london_move"]
    high_bucket = bucket_stats[bucket_stats["percentile_bucket"] == "90-100%"]["median_london_move"]
    low_median = float(low_bucket.iloc[0]) if not low_bucket.isna().all() and len(low_bucket) else float("nan")
    high_median = float(high_bucket.iloc[0]) if not high_bucket.isna().all() and len(high_bucket) else float("nan")

    compression_detected = bool(pd.notna(low_median) and pd.notna(high_median) and low_median > high_median)
    interpretation = "Compression effect detected" if compression_detected else "No meaningful compression effect"

    summary = {
        "days_analyzed": int(len(daily)),
        "correlation_asian_range_vs_london_move": corr,
        "median_london_move_bottom_decile": low_median,
        "median_london_move_top_decile": high_median,
        "interpretation": interpretation,
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("Range compression diagnostics complete")
    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"correlation: {summary['correlation_asian_range_vs_london_move']}")
    print(f"interpretation: {interpretation}")
    print(f"range_stats: {bucket_path}")
    print(f"summary: {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
