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


ATR_PERIOD = 14
STRONG_IMPULSE_ATR_MULTIPLE = 0.7

LONDON_START = time(7, 0)
LONDON_END = time(10, 0)
IMPULSE_START = time(7, 0)
IMPULSE_END = time(7, 45)
PULLBACK_START = time(7, 45)
PULLBACK_END = time(9, 0)
CONTINUATION_START = time(9, 0)
CONTINUATION_END = time(10, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze a refined London pullback-continuation diagnostic on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/london_pullback_continuation_refined_diagnostic",
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


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return float("nan")
    return float(numerator / denominator)


def _direction(impulse_open: float, impulse_close: float) -> str:
    if impulse_close > impulse_open:
        return "bullish"
    if impulse_close < impulse_open:
        return "bearish"
    return "flat"


def compute_daily_metrics(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["atr"] = compute_atr(df)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time

    rows: list[dict[str, object]] = []
    for date, day in df.groupby("date", sort=True):
        london_day = day.loc[_window_mask(day["tod"], LONDON_START, LONDON_END)]
        impulse = day.loc[_window_mask(day["tod"], IMPULSE_START, IMPULSE_END)]
        pullback = day.loc[_window_mask(day["tod"], PULLBACK_START, PULLBACK_END)]
        continuation = day.loc[_window_mask(day["tod"], CONTINUATION_START, CONTINUATION_END)]

        if london_day.empty or impulse.empty or pullback.empty or continuation.empty:
            continue

        impulse_open = float(impulse.iloc[0]["mid_open"])
        impulse_close = float(impulse.iloc[-1]["mid_close"])
        impulse_high = float(impulse["mid_high"].max())
        impulse_low = float(impulse["mid_low"].min())
        impulse_size = abs(impulse_close - impulse_open)

        atr = float(impulse.iloc[-1]["atr"]) if pd.notna(impulse.iloc[-1]["atr"]) else float("nan")
        impulse_to_atr_ratio = _safe_ratio(impulse_size, atr)
        direction = _direction(impulse_open, impulse_close)
        strong = bool(pd.notna(atr) and atr > 0 and impulse_size >= STRONG_IMPULSE_ATR_MULTIPLE * atr)

        pullback_ratio = float("nan")
        continuation_ratio = float("nan")
        if direction == "bullish":
            pullback_abs = max(impulse_high - float(pullback["mid_low"].min()), 0.0)
            continuation_abs = max(float(continuation["mid_high"].max()) - impulse_close, 0.0)
            pullback_ratio = _safe_ratio(pullback_abs, impulse_size)
            continuation_ratio = _safe_ratio(continuation_abs, impulse_size)
        elif direction == "bearish":
            pullback_abs = max(float(pullback["mid_high"].max()) - impulse_low, 0.0)
            continuation_abs = max(impulse_close - float(continuation["mid_low"].min()), 0.0)
            pullback_ratio = _safe_ratio(pullback_abs, impulse_size)
            continuation_ratio = _safe_ratio(continuation_abs, impulse_size)

        rows.append(
            {
                "date": date,
                "impulse_direction": direction,
                "impulse_size": float(impulse_size),
                "atr": atr,
                "impulse_to_atr_ratio": impulse_to_atr_ratio,
                "strong_impulse_flag": strong,
                "pullback_ratio": pullback_ratio,
                "continuation_ratio": continuation_ratio,
            }
        )

    daily = pd.DataFrame(rows)
    if daily.empty:
        raise ValueError("No daily rows produced for the configured windows.")
    return daily.sort_values("date").reset_index(drop=True)


def _safe_quantile(series: pd.Series, q: float) -> float:
    clean = series.dropna()
    if clean.empty:
        return 0.0
    return float(clean.quantile(q))


def distribution_table(daily: pd.DataFrame) -> pd.DataFrame:
    metrics = {
        "impulse_to_atr_ratio": daily["impulse_to_atr_ratio"],
        "pullback_ratio": daily["pullback_ratio"],
        "continuation_ratio": daily["continuation_ratio"],
    }
    rows: list[dict[str, float | str | int]] = []
    for metric, series in metrics.items():
        clean = series.dropna()
        if clean.empty:
            continue
        rows.append(
            {
                "metric": metric,
                "count": int(clean.shape[0]),
                "min": float(clean.min()),
                "p10": float(clean.quantile(0.10)),
                "p25": float(clean.quantile(0.25)),
                "p50": float(clean.quantile(0.50)),
                "p75": float(clean.quantile(0.75)),
                "p90": float(clean.quantile(0.90)),
                "p95": float(clean.quantile(0.95)),
                "max": float(clean.max()),
            }
        )
    return pd.DataFrame(rows)


def classify_diagnostic(summary: dict[str, object]) -> tuple[str, bool]:
    strong_freq = float(summary["strong_impulse_frequency"])
    med_pullback = float(summary["median_pullback_ratio"])
    med_cont = float(summary["median_continuation_ratio"])
    p75_cont = float(summary["p75_continuation_ratio"])
    strong_median_cont = float(summary["strong_impulse_median_continuation_ratio"])

    promising = (
        strong_freq >= 0.20
        and med_pullback < 1.0
        and (med_cont >= 0.50 or p75_cont >= 0.80 or strong_median_cont >= 0.55)
    )
    if promising:
        verdict = "promising_enough_to_implement_mvp"
    else:
        verdict = "researched_but_not_promising"
    return verdict, promising


def build_summary(daily: pd.DataFrame, dataset_path: str) -> dict[str, object]:
    strong = daily[daily["strong_impulse_flag"]]

    summary: dict[str, object] = {
        "dataset": dataset_path,
        "windows_utc": {
            "london": {"start": "07:00", "end_exclusive": "10:00"},
            "impulse": {"start": "07:00", "end_exclusive": "07:45"},
            "pullback": {"start": "07:45", "end_exclusive": "09:00"},
            "continuation": {"start": "09:00", "end_exclusive": "10:00"},
        },
        "days_analyzed": int(len(daily)),
        "strong_impulse_threshold": f"impulse_size >= {STRONG_IMPULSE_ATR_MULTIPLE:.1f} * ATR({ATR_PERIOD})",
        "strong_impulse_frequency": float(daily["strong_impulse_flag"].mean()),
        "bullish_impulse_frequency": float((daily["impulse_direction"] == "bullish").mean()),
        "bearish_impulse_frequency": float((daily["impulse_direction"] == "bearish").mean()),
        "median_impulse_to_atr_ratio": _safe_quantile(daily["impulse_to_atr_ratio"], 0.50),
        "p75_impulse_to_atr_ratio": _safe_quantile(daily["impulse_to_atr_ratio"], 0.75),
        "p90_impulse_to_atr_ratio": _safe_quantile(daily["impulse_to_atr_ratio"], 0.90),
        "median_pullback_ratio": _safe_quantile(daily["pullback_ratio"], 0.50),
        "p75_pullback_ratio": _safe_quantile(daily["pullback_ratio"], 0.75),
        "p90_pullback_ratio": _safe_quantile(daily["pullback_ratio"], 0.90),
        "median_continuation_ratio": _safe_quantile(daily["continuation_ratio"], 0.50),
        "p75_continuation_ratio": _safe_quantile(daily["continuation_ratio"], 0.75),
        "p90_continuation_ratio": _safe_quantile(daily["continuation_ratio"], 0.90),
        "strong_impulse_days": int(len(strong)),
        "strong_impulse_median_continuation_ratio": _safe_quantile(
            strong["continuation_ratio"], 0.50
        ),
        "strong_impulse_p75_continuation_ratio": _safe_quantile(
            strong["continuation_ratio"], 0.75
        ),
        "strong_impulse_p90_continuation_ratio": _safe_quantile(
            strong["continuation_ratio"], 0.90
        ),
    }

    verdict, promising = classify_diagnostic(summary)
    summary["diagnostic_verdict"] = verdict
    summary["promising_enough_for_mvp"] = promising
    return summary


def write_outputs(
    output_dir: Path, daily: pd.DataFrame, dist: pd.DataFrame, summary: dict[str, object]
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    daily.to_csv(output_dir / "daily_metrics.csv", index=False)
    dist.to_csv(output_dir / "distribution.csv", index=False)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    bars = load_bars(args.bars)
    daily = compute_daily_metrics(bars)
    dist = distribution_table(daily)
    summary = build_summary(daily, dataset_path=args.bars)
    out_dir = Path(args.output_dir)
    write_outputs(out_dir, daily, dist, summary)

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"strong_impulse_frequency: {summary['strong_impulse_frequency']:.4f}")
    print(f"bullish_impulse_frequency: {summary['bullish_impulse_frequency']:.4f}")
    print(f"bearish_impulse_frequency: {summary['bearish_impulse_frequency']:.4f}")
    print(f"median_pullback_ratio: {summary['median_pullback_ratio']:.4f}")
    print(f"median_continuation_ratio: {summary['median_continuation_ratio']:.4f}")
    print(
        f"strong_impulse_median_continuation_ratio: "
        f"{summary['strong_impulse_median_continuation_ratio']:.4f}"
    )
    print(f"diagnostic_verdict: {summary['diagnostic_verdict']}")
    print(f"\nSaved outputs in: {out_dir}")


if __name__ == "__main__":
    main()
