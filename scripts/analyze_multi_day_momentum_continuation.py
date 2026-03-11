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


ATR_PERIOD = 14
STRONG_MOMENTUM_ATR_MULTIPLE = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze multi-day momentum continuation on EURUSD daily bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input 15m bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/multi_day_momentum_continuation_diagnostic",
        help="Output directory for summary/distribution/daily_metrics",
    )
    return parser.parse_args()


def aggregate_daily_bars(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date.astype(str)

    daily = (
        df.groupby("date")
        .agg(
            daily_open=("mid_open", "first"),
            daily_high=("mid_high", "max"),
            daily_low=("mid_low", "min"),
            daily_close=("mid_close", "last"),
        )
        .reset_index()
        .sort_values("date")
        .reset_index(drop=True)
    )
    daily["daily_range"] = daily["daily_high"] - daily["daily_low"]
    daily["daily_return"] = daily["daily_close"] - daily["daily_open"]
    return daily


def compute_daily_atr(daily: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    prev_close = daily["daily_close"].shift(1)
    tr = pd.concat(
        [
            (daily["daily_high"] - daily["daily_low"]).abs(),
            (daily["daily_high"] - prev_close).abs(),
            (daily["daily_low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1, skipna=True)
    return tr.rolling(period, min_periods=period).mean()


def _direction(daily_return: float) -> str:
    if daily_return > 0:
        return "bullish_momentum"
    if daily_return < 0:
        return "bearish_momentum"
    return "flat"


def _safe_ratio(numerator: float, denominator: float) -> float:
    if pd.isna(denominator) or denominator == 0.0:
        return float("nan")
    return float(numerator / denominator)


def compute_event_metrics(daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy().reset_index(drop=True)
    out["daily_atr"] = compute_daily_atr(out, period=ATR_PERIOD)
    out["daily_return_atr"] = out["daily_return"].abs() / out["daily_atr"]
    out["direction"] = out["daily_return"].map(_direction)
    out["strong_momentum_flag"] = (
        out["daily_return"].abs() >= STRONG_MOMENTUM_ATR_MULTIPLE * out["daily_atr"]
    )
    out["strong_momentum_flag"] = out["strong_momentum_flag"].fillna(False)

    for horizon in (1, 2, 3):
        out[f"close_plus_{horizon}d"] = out["daily_close"].shift(-horizon)
        out[f"low_next_{horizon}d"] = (
            out["daily_low"]
            .shift(-1)
            .rolling(window=horizon, min_periods=horizon)
            .min()
            .shift(-(horizon - 1))
        )
        out[f"high_next_{horizon}d"] = (
            out["daily_high"]
            .shift(-1)
            .rolling(window=horizon, min_periods=horizon)
            .max()
            .shift(-(horizon - 1))
        )

        continuation_raw = pd.Series(float("nan"), index=out.index, dtype=float)
        bullish_mask = out["direction"] == "bullish_momentum"
        bearish_mask = out["direction"] == "bearish_momentum"
        continuation_raw.loc[bullish_mask] = (
            out.loc[bullish_mask, f"close_plus_{horizon}d"] - out.loc[bullish_mask, "daily_close"]
        )
        continuation_raw.loc[bearish_mask] = (
            out.loc[bearish_mask, "daily_close"] - out.loc[bearish_mask, f"close_plus_{horizon}d"]
        )
        out[f"continuation_{horizon}d"] = continuation_raw
        out[f"continuation_{horizon}d_atr"] = continuation_raw / out["daily_atr"]

        adverse_raw = pd.Series(float("nan"), index=out.index, dtype=float)
        adverse_raw.loc[bullish_mask] = (
            out.loc[bullish_mask, "daily_close"] - out.loc[bullish_mask, f"low_next_{horizon}d"]
        )
        adverse_raw.loc[bearish_mask] = (
            out.loc[bearish_mask, f"high_next_{horizon}d"] - out.loc[bearish_mask, "daily_close"]
        )
        out[f"adverse_{horizon}d"] = adverse_raw
        out[f"adverse_{horizon}d_atr"] = adverse_raw / out["daily_atr"]

    return out


def _safe_quantile(series: pd.Series, q: float) -> float:
    clean = series.dropna()
    if clean.empty:
        return 0.0
    return float(clean.quantile(q))


def _distribution_row(metric: str, series: pd.Series) -> dict[str, float | str | int]:
    clean = series.dropna()
    if clean.empty:
        return {
            "metric": metric,
            "count": 0,
            "min": 0.0,
            "p10": 0.0,
            "p25": 0.0,
            "p50": 0.0,
            "p75": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "max": 0.0,
        }
    return {
        "metric": metric,
        "count": int(len(clean)),
        "min": float(clean.min()),
        "p10": float(clean.quantile(0.10)),
        "p25": float(clean.quantile(0.25)),
        "p50": float(clean.quantile(0.50)),
        "p75": float(clean.quantile(0.75)),
        "p90": float(clean.quantile(0.90)),
        "p95": float(clean.quantile(0.95)),
        "max": float(clean.max()),
    }


def build_distribution(events: pd.DataFrame) -> pd.DataFrame:
    strong = events[events["strong_momentum_flag"]]
    rows = [
        _distribution_row("daily_return_atr", events["daily_return_atr"]),
        _distribution_row("continuation_1d_atr_strong", strong["continuation_1d_atr"]),
        _distribution_row("continuation_2d_atr_strong", strong["continuation_2d_atr"]),
        _distribution_row("continuation_3d_atr_strong", strong["continuation_3d_atr"]),
        _distribution_row("adverse_1d_atr_strong", strong["adverse_1d_atr"]),
        _distribution_row("adverse_2d_atr_strong", strong["adverse_2d_atr"]),
        _distribution_row("adverse_3d_atr_strong", strong["adverse_3d_atr"]),
    ]
    return pd.DataFrame(rows)


def classify_diagnostic(summary: dict[str, object]) -> tuple[str, bool]:
    strong_freq = float(summary["strong_momentum_frequency"])
    c1 = float(summary["median_continuation_1d_atr"])
    c2 = float(summary["median_continuation_2d_atr"])
    c3 = float(summary["median_continuation_3d_atr"])
    bull_1d = float(summary["strong_bullish_median_continuation_1d_atr"])
    bear_1d = float(summary["strong_bearish_median_continuation_1d_atr"])

    asymmetry = abs(bull_1d - bear_1d)
    promising = (
        strong_freq >= 0.10
        and c1 > 0.0
        and c2 > 0.0
        and c3 > 0.0
        and c3 >= c1
        and asymmetry <= 0.50
    )
    verdict = (
        "promising_enough_to_implement_mvp"
        if promising
        else "researched_but_not_promising"
    )
    return verdict, promising


def build_summary(events: pd.DataFrame, dataset_path: str) -> dict[str, object]:
    strong = events[events["strong_momentum_flag"]]
    strong_bull = strong[strong["direction"] == "bullish_momentum"]
    strong_bear = strong[strong["direction"] == "bearish_momentum"]

    summary: dict[str, object] = {
        "dataset": dataset_path,
        "atr_period": ATR_PERIOD,
        "strong_momentum_threshold": f"abs(daily_return) >= {STRONG_MOMENTUM_ATR_MULTIPLE:.1f} * daily_ATR",
        "days_analyzed": int(len(events)),
        "strong_momentum_frequency": float(events["strong_momentum_flag"].mean()),
        "bullish_momentum_frequency": float((events["direction"] == "bullish_momentum").mean()),
        "bearish_momentum_frequency": float((events["direction"] == "bearish_momentum").mean()),
        "median_daily_return_atr": _safe_quantile(events["daily_return_atr"], 0.50),
        "p75_daily_return_atr": _safe_quantile(events["daily_return_atr"], 0.75),
        "p90_daily_return_atr": _safe_quantile(events["daily_return_atr"], 0.90),
        "strong_momentum_days": int(len(strong)),
        "median_continuation_1d_atr": _safe_quantile(strong["continuation_1d_atr"], 0.50),
        "median_continuation_2d_atr": _safe_quantile(strong["continuation_2d_atr"], 0.50),
        "median_continuation_3d_atr": _safe_quantile(strong["continuation_3d_atr"], 0.50),
        "p75_continuation_1d_atr": _safe_quantile(strong["continuation_1d_atr"], 0.75),
        "p75_continuation_2d_atr": _safe_quantile(strong["continuation_2d_atr"], 0.75),
        "p75_continuation_3d_atr": _safe_quantile(strong["continuation_3d_atr"], 0.75),
        "strong_bullish_days": int(len(strong_bull)),
        "strong_bearish_days": int(len(strong_bear)),
        "strong_bullish_median_continuation_1d_atr": _safe_quantile(
            strong_bull["continuation_1d_atr"], 0.50
        ),
        "strong_bearish_median_continuation_1d_atr": _safe_quantile(
            strong_bear["continuation_1d_atr"], 0.50
        ),
    }
    verdict, promising = classify_diagnostic(summary)
    summary["diagnostic_verdict"] = verdict
    summary["promising_enough_for_mvp"] = promising
    return summary


def write_outputs(
    output_dir: Path,
    summary: dict[str, object],
    events: pd.DataFrame,
    distribution: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    export_cols = [
        "date",
        "direction",
        "daily_open",
        "daily_high",
        "daily_low",
        "daily_close",
        "daily_range",
        "daily_return",
        "daily_atr",
        "daily_return_atr",
        "strong_momentum_flag",
        "continuation_1d_atr",
        "continuation_2d_atr",
        "continuation_3d_atr",
        "adverse_1d_atr",
        "adverse_2d_atr",
        "adverse_3d_atr",
    ]
    events[export_cols].to_csv(output_dir / "daily_metrics.csv", index=False)
    distribution.to_csv(output_dir / "distribution.csv", index=False)


def main() -> None:
    args = parse_args()
    bars = load_bars(args.bars)
    daily = aggregate_daily_bars(bars)
    events = compute_event_metrics(daily)
    distribution = build_distribution(events)
    summary = build_summary(events, dataset_path=args.bars)
    output_dir = Path(args.output_dir)
    write_outputs(output_dir, summary, events, distribution)

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"strong_momentum_frequency: {summary['strong_momentum_frequency']:.4f}")
    print(f"median_daily_return_atr: {summary['median_daily_return_atr']:.4f}")
    print(f"median_continuation_1d_atr: {summary['median_continuation_1d_atr']:.4f}")
    print(f"median_continuation_2d_atr: {summary['median_continuation_2d_atr']:.4f}")
    print(f"median_continuation_3d_atr: {summary['median_continuation_3d_atr']:.4f}")
    print(f"diagnostic_verdict: {summary['diagnostic_verdict']}")
    print(f"\nSaved outputs in: {output_dir}")


if __name__ == "__main__":
    main()
