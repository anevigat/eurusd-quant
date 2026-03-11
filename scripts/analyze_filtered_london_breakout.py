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


ASIAN_START = time(0, 0)
ASIAN_END = time(7, 0)
LONDON_START = time(7, 0)
LONDON_END = time(10, 0)
ATR_PERIOD = 14


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze filtered London breakout behavior with compression + close confirmation."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/filtered_london_breakout_diagnostic",
        help="Output directory for summary.json, daily_metrics.csv, distribution.csv",
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


def detect_confirmed_breakout_by_close(
    london: pd.DataFrame, asian_high: float, asian_low: float
) -> tuple[bool, str, pd.Timestamp | pd.NaT, float | None]:
    upside = london[london["mid_close"] > asian_high]
    downside = london[london["mid_close"] < asian_low]

    if upside.empty and downside.empty:
        return False, "none", pd.NaT, None

    first_up_time = upside.iloc[0]["timestamp"] if not upside.empty else pd.NaT
    first_dn_time = downside.iloc[0]["timestamp"] if not downside.empty else pd.NaT

    if not upside.empty and (downside.empty or first_up_time < first_dn_time):
        first = upside.iloc[0]
        return True, "upside", first["timestamp"], float(first["mid_close"])
    if not downside.empty and (upside.empty or first_dn_time < first_up_time):
        first = downside.iloc[0]
        return True, "downside", first["timestamp"], float(first["mid_close"])

    # If exact same timestamp confirms both sides (unlikely), mark none to stay conservative.
    return False, "none", pd.NaT, None


def compute_follow_and_adverse_after_confirmation(
    london: pd.DataFrame,
    confirmed_break_direction: str,
    confirmed_break_time: pd.Timestamp | pd.NaT,
    breakout_close: float | None,
) -> tuple[float, float]:
    if (
        confirmed_break_direction not in {"upside", "downside"}
        or pd.isna(confirmed_break_time)
        or breakout_close is None
    ):
        return float("nan"), float("nan")

    post = london[london["timestamp"] > confirmed_break_time]
    if post.empty:
        return 0.0, 0.0

    if confirmed_break_direction == "upside":
        follow = float(post["mid_high"].max() - breakout_close)
        adverse = float(breakout_close - post["mid_low"].min())
    else:
        follow = float(breakout_close - post["mid_low"].min())
        adverse = float(post["mid_high"].max() - breakout_close)

    return max(follow, 0.0), max(adverse, 0.0)


def compute_daily_metrics(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["atr"] = compute_atr(df)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["tod"] = df["timestamp"].dt.time

    rows: list[dict[str, object]] = []
    for date, day in df.groupby("date", sort=True):
        asian = day[_window_mask(day["tod"], ASIAN_START, ASIAN_END)]
        london = day[_window_mask(day["tod"], LONDON_START, LONDON_END)]
        if asian.empty or london.empty:
            continue

        asian_high = float(asian["mid_high"].max())
        asian_low = float(asian["mid_low"].min())
        asian_range = float(asian_high - asian_low)

        asian_last = asian.iloc[-1]
        atr = float(asian_last["atr"]) if pd.notna(asian_last["atr"]) else float("nan")
        asian_range_atr_ratio = (
            float(asian_range / atr) if pd.notna(atr) and atr > 0 else float("nan")
        )

        confirmed, direction, break_time, breakout_close = detect_confirmed_breakout_by_close(
            london=london[["timestamp", "mid_close", "mid_high", "mid_low"]].copy(),
            asian_high=asian_high,
            asian_low=asian_low,
        )
        follow, adverse = compute_follow_and_adverse_after_confirmation(
            london=london[["timestamp", "mid_close", "mid_high", "mid_low"]].copy(),
            confirmed_break_direction=direction,
            confirmed_break_time=break_time,
            breakout_close=breakout_close,
        )

        if asian_range > 0 and pd.notna(follow):
            follow_r = float(follow / asian_range)
            adverse_r = float(adverse / asian_range)
        else:
            follow_r = float("nan")
            adverse_r = float("nan")

        rows.append(
            {
                "date": date,
                "asian_high": asian_high,
                "asian_low": asian_low,
                "asian_range": asian_range,
                "atr": atr,
                "asian_range_atr_ratio": asian_range_atr_ratio,
                "compressed_day_flag": False,
                "confirmed_breakout_flag": bool(confirmed),
                "confirmed_break_direction": direction,
                "confirmed_break_time": break_time.isoformat() if pd.notna(break_time) else None,
                "breakout_close": breakout_close,
                "follow_through_R": follow_r,
                "adverse_move_R": adverse_r,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("No daily rows were produced from the input bars.")
    return out.sort_values("date").reset_index(drop=True)


def assign_compression_flag(
    daily: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float]]:
    out = daily.copy()
    clean = out["asian_range_atr_ratio"].dropna()
    if clean.empty:
        out["compressed_day_flag"] = False
        return out, {"p10": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0}

    quantiles = {
        "p10": float(clean.quantile(0.10)),
        "p25": float(clean.quantile(0.25)),
        "p50": float(clean.quantile(0.50)),
        "p75": float(clean.quantile(0.75)),
        "p90": float(clean.quantile(0.90)),
    }
    out["compressed_day_flag"] = out["asian_range_atr_ratio"] <= quantiles["p25"]
    out["compressed_day_flag"] = out["compressed_day_flag"].fillna(False)
    return out, quantiles


def _safe_quantile(series: pd.Series, q: float) -> float:
    clean = series.dropna()
    if clean.empty:
        return 0.0
    return float(clean.quantile(q))


def _direction_stats(df: pd.DataFrame, direction: str) -> dict[str, float | int | str]:
    subset = df[df["confirmed_break_direction"] == direction]
    return {
        "direction": direction,
        "count": int(len(subset)),
        "median_follow_through_R": _safe_quantile(subset["follow_through_R"], 0.50),
        "median_adverse_move_R": _safe_quantile(subset["adverse_move_R"], 0.50),
    }


def classify_diagnostic(summary: dict[str, object]) -> tuple[str, bool]:
    compressed_freq = float(summary["compressed_day_frequency"])
    confirmed_on_compressed = float(summary["confirmed_breakout_frequency_on_compressed_days"])
    med_follow_compressed = float(summary["median_follow_through_R_compressed_days"])
    med_adverse_compressed = float(summary["median_adverse_move_R_compressed_days"])

    promising = (
        compressed_freq >= 0.10
        and confirmed_on_compressed >= 0.20
        and med_follow_compressed > 0.0
        and med_follow_compressed >= med_adverse_compressed
    )
    verdict = (
        "promising_enough_to_implement_mvp"
        if promising
        else "researched_but_not_promising"
    )
    return verdict, promising


def build_summary(
    daily: pd.DataFrame, dataset_path: str, compression_quantiles: dict[str, float]
) -> dict[str, object]:
    confirmed_all = daily[daily["confirmed_breakout_flag"]]
    compressed = daily[daily["compressed_day_flag"]]
    confirmed_compressed = compressed[compressed["confirmed_breakout_flag"]]

    summary: dict[str, object] = {
        "dataset": dataset_path,
        "windows_utc": {
            "asian": {"start": "00:00", "end_exclusive": "07:00"},
            "london": {"start": "07:00", "end_exclusive": "10:00"},
        },
        "atr_period": ATR_PERIOD,
        "compression_definition": "compressed_day if asian_range_atr_ratio <= p25",
        "asian_range_atr_ratio_quantiles": compression_quantiles,
        "days_analyzed": int(len(daily)),
        "compressed_day_frequency": float(compressed.shape[0] / daily.shape[0]) if len(daily) else 0.0,
        "confirmed_breakout_frequency_on_all_days": float(confirmed_all.shape[0] / daily.shape[0])
        if len(daily)
        else 0.0,
        "confirmed_breakout_frequency_on_compressed_days": float(
            confirmed_compressed.shape[0] / compressed.shape[0]
        )
        if len(compressed)
        else 0.0,
        "median_follow_through_R_all_days": _safe_quantile(confirmed_all["follow_through_R"], 0.50),
        "median_adverse_move_R_all_days": _safe_quantile(confirmed_all["adverse_move_R"], 0.50),
        "median_follow_through_R_compressed_days": _safe_quantile(
            confirmed_compressed["follow_through_R"], 0.50
        ),
        "p75_follow_through_R_compressed_days": _safe_quantile(
            confirmed_compressed["follow_through_R"], 0.75
        ),
        "p90_follow_through_R_compressed_days": _safe_quantile(
            confirmed_compressed["follow_through_R"], 0.90
        ),
        "median_adverse_move_R_compressed_days": _safe_quantile(
            confirmed_compressed["adverse_move_R"], 0.50
        ),
        "direction_breakdown_all_days": [
            _direction_stats(confirmed_all, "upside"),
            _direction_stats(confirmed_all, "downside"),
        ],
        "direction_breakdown_compressed_days": [
            _direction_stats(confirmed_compressed, "upside"),
            _direction_stats(confirmed_compressed, "downside"),
        ],
    }

    verdict, promising = classify_diagnostic(summary)
    summary["diagnostic_verdict"] = verdict
    summary["promising_enough_for_mvp"] = promising
    return summary


def build_distribution(daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | str | int]] = []
    ratio = daily["asian_range_atr_ratio"].dropna()
    if not ratio.empty:
        rows.append(
            {
                "section": "asian_range_atr_ratio",
                "metric": "count",
                "value": int(len(ratio)),
            }
        )
        for q_name, q_value in (
            ("min", float(ratio.min())),
            ("p10", float(ratio.quantile(0.10))),
            ("p25", float(ratio.quantile(0.25))),
            ("p50", float(ratio.quantile(0.50))),
            ("p75", float(ratio.quantile(0.75))),
            ("p90", float(ratio.quantile(0.90))),
            ("max", float(ratio.max())),
        ):
            rows.append(
                {
                    "section": "asian_range_atr_ratio",
                    "metric": q_name,
                    "value": q_value,
                }
            )

    confirmed = daily[daily["confirmed_breakout_flag"]]
    confirmed_compressed = daily[daily["compressed_day_flag"] & daily["confirmed_breakout_flag"]]
    rows.extend(
        [
            {
                "section": "breakout_counts",
                "metric": "confirmed_all_days",
                "value": int(len(confirmed)),
            },
            {
                "section": "breakout_counts",
                "metric": "confirmed_compressed_days",
                "value": int(len(confirmed_compressed)),
            },
            {
                "section": "follow_through_R",
                "metric": "median_confirmed_all_days",
                "value": _safe_quantile(confirmed["follow_through_R"], 0.50),
            },
            {
                "section": "follow_through_R",
                "metric": "median_confirmed_compressed_days",
                "value": _safe_quantile(confirmed_compressed["follow_through_R"], 0.50),
            },
            {
                "section": "adverse_move_R",
                "metric": "median_confirmed_all_days",
                "value": _safe_quantile(confirmed["adverse_move_R"], 0.50),
            },
            {
                "section": "adverse_move_R",
                "metric": "median_confirmed_compressed_days",
                "value": _safe_quantile(confirmed_compressed["adverse_move_R"], 0.50),
            },
        ]
    )
    return pd.DataFrame(rows)


def write_outputs(
    output_dir: Path, summary: dict[str, object], daily: pd.DataFrame, distribution: pd.DataFrame
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    export_cols = [
        "date",
        "asian_range",
        "atr",
        "asian_range_atr_ratio",
        "compressed_day_flag",
        "confirmed_breakout_flag",
        "confirmed_break_direction",
        "confirmed_break_time",
        "follow_through_R",
        "adverse_move_R",
    ]
    daily[export_cols].to_csv(output_dir / "daily_metrics.csv", index=False)
    distribution.to_csv(output_dir / "distribution.csv", index=False)


def main() -> None:
    args = parse_args()
    bars = load_bars(args.bars)
    daily = compute_daily_metrics(bars)
    daily, quantiles = assign_compression_flag(daily)
    distribution = build_distribution(daily)
    summary = build_summary(daily, dataset_path=args.bars, compression_quantiles=quantiles)
    output_dir = Path(args.output_dir)
    write_outputs(output_dir, summary, daily, distribution)

    print(f"days_analyzed: {summary['days_analyzed']}")
    print(f"compressed_day_frequency: {summary['compressed_day_frequency']:.4f}")
    print(
        "confirmed_breakout_frequency_on_all_days: "
        f"{summary['confirmed_breakout_frequency_on_all_days']:.4f}"
    )
    print(
        "confirmed_breakout_frequency_on_compressed_days: "
        f"{summary['confirmed_breakout_frequency_on_compressed_days']:.4f}"
    )
    print(
        f"median_follow_through_R_compressed_days: "
        f"{summary['median_follow_through_R_compressed_days']:.4f}"
    )
    print(
        f"median_adverse_move_R_compressed_days: "
        f"{summary['median_adverse_move_R_compressed_days']:.4f}"
    )
    print(f"diagnostic_verdict: {summary['diagnostic_verdict']}")
    print(f"\nSaved outputs in: {output_dir}")


if __name__ == "__main__":
    main()
