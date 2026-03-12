from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.data.loaders import load_bars


Direction = Literal["up", "down", "none"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze forward returns after reusable event families on EURUSD M15 bars."
    )
    parser.add_argument(
        "--bars",
        default="data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Input bars parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/event_return_analyzer",
        help="Directory for summary.json, event_returns.csv, event_bucket_summary.csv",
    )
    parser.add_argument("--atr-period", type=int, default=14, help="ATR period")
    parser.add_argument(
        "--impulse-lookback-bars",
        type=int,
        default=4,
        help="Lookback bars for impulse move events",
    )
    parser.add_argument(
        "--breakout-lookback-bars",
        type=int,
        default=20,
        help="Lookback bars for new-high/new-low events",
    )
    parser.add_argument(
        "--compression-window-bars",
        type=int,
        default=40,
        help="Rolling window for ATR median in compression events",
    )
    parser.add_argument(
        "--min-sample-size",
        type=int,
        default=30,
        help="Minimum sample size for top bucket ranking in summary",
    )
    return parser.parse_args()


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["mid_close"].shift(1)
    tr = pd.concat(
        [
            df["mid_high"] - df["mid_low"],
            (df["mid_high"] - prev_close).abs(),
            (df["mid_low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def impulse_bucket(strength_atr: float) -> str | None:
    if not np.isfinite(strength_atr):
        return None
    if 1.0 <= strength_atr < 1.5:
        return "1.0-1.5_atr"
    if 1.5 <= strength_atr < 2.0:
        return "1.5-2.0_atr"
    if strength_atr >= 2.0:
        return ">2.0_atr"
    return None


def compression_bucket(
    ratio: float, p10: float, p25: float, p50: float
) -> str | None:
    if not np.isfinite(ratio):
        return None
    if ratio <= p10:
        return "<=p10"
    if p10 < ratio <= p25:
        return "p10-p25"
    if p25 < ratio <= p50:
        return "p25-p50"
    return None


def direction_sign(direction: Direction) -> int | None:
    if direction == "up":
        return 1
    if direction == "down":
        return -1
    return None


def _forward_return(
    close_now: float,
    close_future: float,
    atr_now: float,
    sign: int | None,
) -> float:
    if not np.isfinite(close_future) or atr_now <= 0:
        return np.nan
    value = (close_future - close_now) / atr_now
    if sign is None:
        return value
    return sign * value


def _adverse_move(
    close_now: float,
    future_highs: np.ndarray,
    future_lows: np.ndarray,
    atr_now: float,
    sign: int | None,
) -> float:
    if len(future_highs) == 0 or atr_now <= 0:
        return np.nan
    if sign == 1:
        return max(0.0, (close_now - float(np.min(future_lows))) / atr_now)
    if sign == -1:
        return max(0.0, (float(np.max(future_highs)) - close_now) / atr_now)

    up_risk = max(0.0, (float(np.max(future_highs)) - close_now) / atr_now)
    down_risk = max(0.0, (close_now - float(np.min(future_lows))) / atr_now)
    return max(up_risk, down_risk)


def compute_forward_metrics(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    atr: np.ndarray,
    idx: int,
    direction: Direction,
) -> dict[str, float]:
    sign = direction_sign(direction)
    close_now = float(closes[idx])
    atr_now = float(atr[idx])
    return {
        "return_1_bar": _forward_return(
            close_now,
            float(closes[idx + 1]) if idx + 1 < len(closes) else np.nan,
            atr_now,
            sign,
        ),
        "return_4_bars": _forward_return(
            close_now,
            float(closes[idx + 4]) if idx + 4 < len(closes) else np.nan,
            atr_now,
            sign,
        ),
        "return_8_bars": _forward_return(
            close_now,
            float(closes[idx + 8]) if idx + 8 < len(closes) else np.nan,
            atr_now,
            sign,
        ),
        "adverse_move_4_bars": _adverse_move(
            close_now,
            highs[idx + 1 : idx + 5],
            lows[idx + 1 : idx + 5],
            atr_now,
            sign,
        ),
        "adverse_move_8_bars": _adverse_move(
            close_now,
            highs[idx + 1 : idx + 9],
            lows[idx + 1 : idx + 9],
            atr_now,
            sign,
        ),
    }


def detect_events(
    df: pd.DataFrame,
    impulse_lookback_bars: int,
    breakout_lookback_bars: int,
    compression_window_bars: int,
) -> pd.DataFrame:
    work = df.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    work = work.sort_values("timestamp").reset_index(drop=True)
    work["atr"] = compute_atr(work, period=14)
    work["rolling_median_atr"] = work["atr"].rolling(
        compression_window_bars, min_periods=compression_window_bars
    ).median()
    work["compression_ratio"] = work["atr"] / work["rolling_median_atr"]

    compression_valid = work["compression_ratio"].dropna()
    if compression_valid.empty:
        raise ValueError("Compression ratio has no valid values")
    p10 = float(compression_valid.quantile(0.10))
    p25 = float(compression_valid.quantile(0.25))
    p50 = float(compression_valid.quantile(0.50))

    timestamps = work["timestamp"].to_numpy()
    closes = work["mid_close"].to_numpy(dtype=float)
    highs = work["mid_high"].to_numpy(dtype=float)
    lows = work["mid_low"].to_numpy(dtype=float)
    atr = work["atr"].to_numpy(dtype=float)
    compression_ratio = work["compression_ratio"].to_numpy(dtype=float)
    n = len(work)

    rows: list[dict[str, object]] = []
    for i in range(n):
        if i + 8 >= n:
            break
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue

        # 1) Impulse events
        if i >= impulse_lookback_bars:
            move = closes[i] - closes[i - impulse_lookback_bars]
            strength_atr = abs(move) / atr[i]
            bucket = impulse_bucket(strength_atr)
            if bucket is not None and move != 0:
                direction: Direction = "up" if move > 0 else "down"
                rows.append(
                    {
                        "timestamp": pd.Timestamp(timestamps[i]).isoformat(),
                        "event_family": "impulse_events",
                        "event_name": f"impulse_{impulse_lookback_bars}bar",
                        "bucket": bucket,
                        "direction": direction,
                        "event_strength_raw": abs(float(move)),
                        "event_strength_atr": float(strength_atr),
                        **compute_forward_metrics(closes, highs, lows, atr, i, direction),
                    }
                )

        # 2) Range compression events
        bucket = compression_bucket(float(compression_ratio[i]), p10, p25, p50)
        if bucket is not None:
            rows.append(
                {
                    "timestamp": pd.Timestamp(timestamps[i]).isoformat(),
                    "event_family": "range_compression_events",
                    "event_name": "atr_compression",
                    "bucket": bucket,
                    "direction": "none",
                    "event_strength_raw": float(compression_ratio[i]),
                    "event_strength_atr": np.nan,
                    **compute_forward_metrics(closes, highs, lows, atr, i, "none"),
                }
            )

        # 3) New high / new low events
        if i >= breakout_lookback_bars:
            prev_high = float(np.max(highs[i - breakout_lookback_bars : i]))
            prev_low = float(np.min(lows[i - breakout_lookback_bars : i]))
            if highs[i] > prev_high:
                raw = highs[i] - prev_high
                rows.append(
                    {
                        "timestamp": pd.Timestamp(timestamps[i]).isoformat(),
                        "event_family": "new_high_low_events",
                        "event_name": f"new_high_{breakout_lookback_bars}",
                        "bucket": "all",
                        "direction": "up",
                        "event_strength_raw": float(raw),
                        "event_strength_atr": float(raw / atr[i]),
                        **compute_forward_metrics(closes, highs, lows, atr, i, "up"),
                    }
                )
            if lows[i] < prev_low:
                raw = prev_low - lows[i]
                rows.append(
                    {
                        "timestamp": pd.Timestamp(timestamps[i]).isoformat(),
                        "event_family": "new_high_low_events",
                        "event_name": f"new_low_{breakout_lookback_bars}",
                        "bucket": "all",
                        "direction": "down",
                        "event_strength_raw": float(raw),
                        "event_strength_atr": float(raw / atr[i]),
                        **compute_forward_metrics(closes, highs, lows, atr, i, "down"),
                    }
                )

        # 4) Session open events
        ts = pd.Timestamp(timestamps[i])
        if ts.hour == 7 and ts.minute == 0:
            rows.append(
                {
                    "timestamp": ts.isoformat(),
                    "event_family": "session_open_events",
                    "event_name": "london_open",
                    "bucket": "all",
                    "direction": "none",
                    "event_strength_raw": np.nan,
                    "event_strength_atr": np.nan,
                    **compute_forward_metrics(closes, highs, lows, atr, i, "none"),
                }
            )
        if ts.hour == 13 and ts.minute == 0:
            rows.append(
                {
                    "timestamp": ts.isoformat(),
                    "event_family": "session_open_events",
                    "event_name": "new_york_open",
                    "bucket": "all",
                    "direction": "none",
                    "event_strength_raw": np.nan,
                    "event_strength_atr": np.nan,
                    **compute_forward_metrics(closes, highs, lows, atr, i, "none"),
                }
            )

    events = pd.DataFrame(rows)
    if events.empty:
        raise ValueError("No events detected")
    return events


def build_event_bucket_summary(events: pd.DataFrame) -> pd.DataFrame:
    summary = (
        events.groupby(
            ["event_family", "event_name", "bucket", "direction"], dropna=False
        )
        .agg(
            sample_size=("timestamp", "count"),
            median_return_1_bar=("return_1_bar", "median"),
            median_return_4_bars=("return_4_bars", "median"),
            median_return_8_bars=("return_8_bars", "median"),
            p25_return_4_bars=("return_4_bars", lambda s: float(s.quantile(0.25))),
            p75_return_4_bars=("return_4_bars", lambda s: float(s.quantile(0.75))),
            median_adverse_move_4_bars=("adverse_move_4_bars", "median"),
            median_adverse_move_8_bars=("adverse_move_8_bars", "median"),
        )
        .reset_index()
    )
    return summary.sort_values(
        ["event_family", "event_name", "bucket", "direction"]
    ).reset_index(drop=True)


def build_summary_json(
    events: pd.DataFrame, bucket_summary: pd.DataFrame, min_sample_size: int
) -> dict[str, object]:
    totals = (
        events.groupby("event_family")["timestamp"].count().sort_values(ascending=False)
    )

    eligible = bucket_summary[bucket_summary["sample_size"] >= min_sample_size].copy()
    if eligible.empty:
        strongest_positive: list[dict[str, object]] = []
        strongest_negative: list[dict[str, object]] = []
        strongest_abs: list[dict[str, object]] = []
    else:
        strongest_positive = (
            eligible.sort_values("median_return_4_bars", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )
        strongest_negative = (
            eligible.sort_values("median_return_4_bars", ascending=True)
            .head(5)
            .to_dict(orient="records")
        )
        abs_rank = eligible.copy()
        abs_rank["abs_median_return_4_bars"] = abs_rank["median_return_4_bars"].abs()
        strongest_abs = (
            abs_rank.sort_values("abs_median_return_4_bars", ascending=False)
            .head(10)
            .to_dict(orient="records")
        )

    return {
        "total_events": int(len(events)),
        "total_events_by_family": {k: int(v) for k, v in totals.items()},
        "sample_size_threshold": int(min_sample_size),
        "strongest_positive_continuation_buckets": strongest_positive,
        "strongest_negative_reversal_buckets": strongest_negative,
        "strongest_absolute_buckets": strongest_abs,
        "interpretation_notes": [
            "positive median_return_4_bars implies continuation in event direction when direction is up/down",
            "negative median_return_4_bars implies reversal against event direction when direction is up/down",
            "for direction=none events, returns are unaligned close-to-close moves in ATR units",
            "buckets below sample_size_threshold should be treated as exploratory only",
        ],
    }


def run_analysis(
    bars_path: str,
    output_dir: str,
    atr_period: int,
    impulse_lookback_bars: int,
    breakout_lookback_bars: int,
    compression_window_bars: int,
    min_sample_size: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    bars = load_bars(bars_path).copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)

    # Fixed to v1 ATR(14) methodology requested.
    _ = atr_period
    events = detect_events(
        bars,
        impulse_lookback_bars=impulse_lookback_bars,
        breakout_lookback_bars=breakout_lookback_bars,
        compression_window_bars=compression_window_bars,
    )
    bucket_summary = build_event_bucket_summary(events)
    summary = build_summary_json(events, bucket_summary, min_sample_size=min_sample_size)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "event_returns.csv"
    bucket_path = out_dir / "event_bucket_summary.csv"
    summary_path = out_dir / "summary.json"

    events.to_csv(events_path, index=False)
    bucket_summary.to_csv(bucket_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return events, bucket_summary, summary


def print_console_summary(bucket_summary: pd.DataFrame, min_sample_size: int) -> None:
    eligible = bucket_summary[bucket_summary["sample_size"] >= min_sample_size].copy()
    if eligible.empty:
        print("No buckets meet sample size threshold for console ranking.")
        return
    eligible["abs_median_return_4_bars"] = eligible["median_return_4_bars"].abs()
    table = eligible.sort_values("abs_median_return_4_bars", ascending=False).head(12)[
        [
            "event_family",
            "event_name",
            "bucket",
            "direction",
            "sample_size",
            "median_return_4_bars",
            "median_adverse_move_4_bars",
        ]
    ]
    print("\nTop event buckets by |median_return_4_bars|:")
    print(table.to_string(index=False))


def main() -> None:
    args = parse_args()
    events, bucket_summary, summary = run_analysis(
        bars_path=args.bars,
        output_dir=args.output_dir,
        atr_period=args.atr_period,
        impulse_lookback_bars=args.impulse_lookback_bars,
        breakout_lookback_bars=args.breakout_lookback_bars,
        compression_window_bars=args.compression_window_bars,
        min_sample_size=args.min_sample_size,
    )

    print(f"total_events: {len(events)}")
    print(f"event_families: {', '.join(sorted(events['event_family'].unique()))}")
    print(f"summary saved: {Path(args.output_dir) / 'summary.json'}")
    print(f"event returns saved: {Path(args.output_dir) / 'event_returns.csv'}")
    print(f"bucket summary saved: {Path(args.output_dir) / 'event_bucket_summary.csv'}")
    print_console_summary(bucket_summary, min_sample_size=args.min_sample_size)
    print("\nSummary highlights:")
    print(f"sample_size_threshold: {summary['sample_size_threshold']}")
    print(
        f"strongest_positive_count: {len(summary['strongest_positive_continuation_buckets'])}, "
        f"strongest_negative_count: {len(summary['strongest_negative_reversal_buckets'])}"
    )


if __name__ == "__main__":
    main()
