from __future__ import annotations

import argparse
import json
import math
from datetime import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_OUTPUT_ROOT = "outputs/event_combination_analysis_v2"
DEFAULT_ALIGNMENT_WINDOW_BARS = 1
DEFAULT_MIN_SAMPLE_SIZE = 200

EXPECTED_DATASETS = {
    "EURUSD_historical": "data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
    "GBPUSD_historical": "data/bars/15m/gbpusd_bars_15m_2018_2024.parquet",
    "EURUSD_forward": "data/bars/15m/eurusd_bars_15m_2025_now.parquet",
    "GBPUSD_forward": "data/bars/15m/gbpusd_bars_15m_2025_now.parquet",
}

BAR_COLUMNS = [
    "timestamp",
    "symbol",
    "timeframe",
    "bid_open",
    "bid_high",
    "bid_low",
    "bid_close",
    "ask_open",
    "ask_high",
    "ask_low",
    "ask_close",
    "mid_open",
    "mid_high",
    "mid_low",
    "mid_close",
    "spread_open",
    "spread_high",
    "spread_low",
    "spread_close",
    "session_label",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Event Combination Analysis v2 across detected FX pair datasets.")
    parser.add_argument(
        "--output-root",
        default=DEFAULT_OUTPUT_ROOT,
        help="Root output directory for per-dataset v2 outputs",
    )
    parser.add_argument(
        "--alignment-window-bars",
        type=int,
        default=DEFAULT_ALIGNMENT_WINDOW_BARS,
        help="Combination alignment rule: same bar (0) or within N bars",
    )
    parser.add_argument(
        "--min-sample-size",
        type=int,
        default=DEFAULT_MIN_SAMPLE_SIZE,
        help="Minimum sample size for top edge ranking",
    )
    return parser.parse_args()


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
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


def detect_available_datasets() -> tuple[dict[str, Path], dict[str, str]]:
    available: dict[str, Path] = {}
    missing: dict[str, str] = {}
    for label, raw_path in EXPECTED_DATASETS.items():
        path = Path(raw_path)
        if path.exists():
            available[label] = path
        else:
            missing[label] = str(path)
    return available, missing


def load_bars_any_symbol(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    missing = [c for c in BAR_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path} missing required columns: {missing}")
    bars = df[BAR_COLUMNS].copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    if not bars["timestamp"].is_monotonic_increasing:
        bars = bars.sort_values("timestamp")
    bars = bars.reset_index(drop=True)
    if (bars["timeframe"] != "15m").any():
        raise ValueError(f"{path} contains non-15m bars")
    return bars


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


def aligned_any(mask: np.ndarray, idx: int, window: int) -> bool:
    left = max(0, idx - window)
    right = min(len(mask), idx + window + 1)
    return bool(mask[left:right].any())


def build_feature_frame(
    bars: pd.DataFrame,
    *,
    impulse_lookback: int = 4,
    breakout_lookback: int = 20,
    atr_median_window: int = 40,
) -> pd.DataFrame:
    df = bars.copy()
    df["atr"] = compute_atr(df, period=14)
    df["rolling_median_atr"] = df["atr"].rolling(atr_median_window, min_periods=atr_median_window).median()
    df["compression_ratio"] = df["atr"] / df["rolling_median_atr"]
    df["atr_ratio"] = df["compression_ratio"]

    df["typical_price"] = (df["mid_high"] + df["mid_low"] + df["mid_close"]) / 3.0
    day = df["timestamp"].dt.floor("D")
    df["intraday_vwap_proxy"] = df.groupby(day)["typical_price"].cumsum() / (df.groupby(day).cumcount() + 1)
    df["vwap_deviation"] = df["mid_close"] - df["intraday_vwap_proxy"]
    df["vwap_deviation_atr"] = df["vwap_deviation"] / df["atr"]

    df["close_lag_impulse"] = df["mid_close"].shift(impulse_lookback)
    df["impulse_move"] = df["mid_close"] - df["close_lag_impulse"]
    df["impulse_strength_atr"] = df["impulse_move"].abs() / df["atr"]
    df["impulse_bucket"] = df["impulse_strength_atr"].map(impulse_bucket)
    df["impulse_direction"] = np.where(
        df["impulse_move"] > 0,
        "up",
        np.where(df["impulse_move"] < 0, "down", "none"),
    )

    df["prev_high_20"] = df["mid_high"].rolling(breakout_lookback).max().shift(1)
    df["prev_low_20"] = df["mid_low"].rolling(breakout_lookback).min().shift(1)
    df["new_high_20"] = df["mid_high"] > df["prev_high_20"]
    df["new_low_20"] = df["mid_low"] < df["prev_low_20"]

    comp_valid = df["compression_ratio"].dropna()
    p10 = float(comp_valid.quantile(0.10)) if not comp_valid.empty else np.nan
    p25 = float(comp_valid.quantile(0.25)) if not comp_valid.empty else np.nan
    p50 = float(comp_valid.quantile(0.50)) if not comp_valid.empty else np.nan
    df["compression_bucket"] = np.select(
        [
            df["compression_ratio"] <= p10,
            (df["compression_ratio"] > p10) & (df["compression_ratio"] <= p25),
            (df["compression_ratio"] > p25) & (df["compression_ratio"] <= p50),
        ],
        ["<=p10", "p10-p25", "p25-p50"],
        default=None,
    )

    df["atr_spike_bucket"] = np.select(
        [df["atr_ratio"] > 2.0, df["atr_ratio"] > 1.5],
        [">2.0", ">1.5"],
        default=None,
    )

    abs_dev = df["vwap_deviation_atr"].abs()
    df["vwap_dev_bucket"] = np.select(
        [abs_dev > 3.0, (abs_dev >= 2.0) & (abs_dev <= 3.0)],
        [">3.0_atr", "2.0-3.0_atr"],
        default=None,
    )
    df["vwap_dev_direction"] = np.where(
        df["vwap_deviation_atr"] > 0,
        "positive",
        np.where(df["vwap_deviation_atr"] < 0, "negative", "none"),
    )

    ts = df["timestamp"]
    df["is_london_open"] = (ts.dt.hour == 7) & (ts.dt.minute == 0)
    df["is_new_york_open"] = (ts.dt.hour == 13) & (ts.dt.minute == 0)

    # Prior-day high/low breaks
    df["date"] = ts.dt.date
    daily = df.groupby("date", as_index=False).agg(day_high=("mid_high", "max"), day_low=("mid_low", "min"))
    daily["prior_day_high"] = daily["day_high"].shift(1)
    daily["prior_day_low"] = daily["day_low"].shift(1)
    prior = daily[["date", "prior_day_high", "prior_day_low"]]
    df = df.merge(prior, on="date", how="left").drop(columns=["date"])
    df["break_above_prior_day_high"] = df["mid_high"] > df["prior_day_high"]
    df["break_below_prior_day_low"] = df["mid_low"] < df["prior_day_low"]

    # Conditional enrichment factors.
    atr_p70 = float(df["atr"].quantile(0.70))
    df["atr_regime"] = np.where(df["atr"] >= atr_p70, "high_atr", "normal_atr")
    t = ts.dt.time
    df["session_regime"] = np.select(
        [
            (t >= time(7, 0)) & (t < time(12, 0)),
            (t >= time(13, 0)) & (t < time(17, 0)),
        ],
        ["london_session", "new_york_session"],
        default="other_session",
    )
    df["impulse_size_regime"] = np.select(
        [df["impulse_bucket"] == ">2.0_atr", df["impulse_bucket"] == "1.5-2.0_atr"],
        ["large_impulse", "medium_impulse"],
        default="none",
    )
    return df


def direction_sign(direction: str) -> int | None:
    if direction == "up":
        return 1
    if direction == "down":
        return -1
    return None


def _forward_return(close_now: float, close_future: float, atr_now: float, sign: int | None) -> float:
    if not np.isfinite(close_future) or not np.isfinite(atr_now) or atr_now <= 0:
        return np.nan
    value = (close_future - close_now) / atr_now
    if sign is None:
        return float(value)
    return float(sign * value)


def _adverse_move(
    close_now: float,
    future_highs: np.ndarray,
    future_lows: np.ndarray,
    atr_now: float,
    sign: int | None,
) -> float:
    if len(future_highs) == 0 or not np.isfinite(atr_now) or atr_now <= 0:
        return np.nan
    if sign == 1:
        return float(max(0.0, (close_now - float(np.min(future_lows))) / atr_now))
    if sign == -1:
        return float(max(0.0, (float(np.max(future_highs)) - close_now) / atr_now))
    up_risk = max(0.0, (float(np.max(future_highs)) - close_now) / atr_now)
    down_risk = max(0.0, (close_now - float(np.min(future_lows))) / atr_now)
    return float(max(up_risk, down_risk))


def compute_forward_metrics(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    atr: np.ndarray,
    idx: int,
    direction: str,
) -> dict[str, float]:
    sign = direction_sign(direction)
    close_now = float(closes[idx])
    atr_now = float(atr[idx])
    return {
        "return_1_bar": _forward_return(close_now, closes[idx + 1] if idx + 1 < len(closes) else np.nan, atr_now, sign),
        "return_4_bars": _forward_return(close_now, closes[idx + 4] if idx + 4 < len(closes) else np.nan, atr_now, sign),
        "return_8_bars": _forward_return(close_now, closes[idx + 8] if idx + 8 < len(closes) else np.nan, atr_now, sign),
        "return_16_bars": _forward_return(close_now, closes[idx + 16] if idx + 16 < len(closes) else np.nan, atr_now, sign),
        "adverse_move_4_bars": _adverse_move(close_now, highs[idx + 1 : idx + 5], lows[idx + 1 : idx + 5], atr_now, sign),
        "adverse_move_8_bars": _adverse_move(close_now, highs[idx + 1 : idx + 9], lows[idx + 1 : idx + 9], atr_now, sign),
        "adverse_move_16_bars": _adverse_move(close_now, highs[idx + 1 : idx + 17], lows[idx + 1 : idx + 17], atr_now, sign),
    }


def detect_pairwise_combinations(df: pd.DataFrame, alignment_window_bars: int) -> pd.DataFrame:
    closes = df["mid_close"].to_numpy(dtype=float)
    highs = df["mid_high"].to_numpy(dtype=float)
    lows = df["mid_low"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)

    impulse_up = (df["impulse_direction"] == "up").to_numpy()
    impulse_down = (df["impulse_direction"] == "down").to_numpy()
    new_high = df["new_high_20"].fillna(False).to_numpy()
    new_low = df["new_low_20"].fillna(False).to_numpy()
    compression = df["compression_bucket"].notna().to_numpy()
    london_open = df["is_london_open"].fillna(False).to_numpy()
    ny_open = df["is_new_york_open"].fillna(False).to_numpy()
    prior_up = df["break_above_prior_day_high"].fillna(False).to_numpy()
    prior_down = df["break_below_prior_day_low"].fillna(False).to_numpy()
    atr_spike = df["atr_spike_bucket"].notna().to_numpy()
    vwap_dev_pos = ((df["vwap_dev_bucket"].notna()) & (df["vwap_dev_direction"] == "positive")).to_numpy()
    vwap_dev_neg = ((df["vwap_dev_bucket"].notna()) & (df["vwap_dev_direction"] == "negative")).to_numpy()

    rows: list[dict[str, Any]] = []
    for i in range(len(df)):
        if i + 16 >= len(df):
            break
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue

        ts = pd.Timestamp(df.iloc[i]["timestamp"])
        cond_session = {
            "session_regime": str(df.iloc[i]["session_regime"]),
            "atr_regime": str(df.iloc[i]["atr_regime"]),
            "impulse_size_regime": str(df.iloc[i]["impulse_size_regime"]),
        }

        def add_event(name: str, direction: str, bucket: str) -> None:
            rows.append(
                {
                    "timestamp": ts.isoformat(),
                    "combination_name": name,
                    "direction": direction,
                    "bucket": bucket,
                    **cond_session,
                    **compute_forward_metrics(closes, highs, lows, atr, i, direction),
                }
            )

        # impulse × session_open
        if aligned_any(impulse_up, i, alignment_window_bars) and (
            aligned_any(london_open, i, alignment_window_bars) or aligned_any(ny_open, i, alignment_window_bars)
        ):
            open_bucket = "london_open" if aligned_any(london_open, i, alignment_window_bars) else "new_york_open"
            add_event("impulse_x_session_open", "up", open_bucket)
        if aligned_any(impulse_down, i, alignment_window_bars) and (
            aligned_any(london_open, i, alignment_window_bars) or aligned_any(ny_open, i, alignment_window_bars)
        ):
            open_bucket = "london_open" if aligned_any(london_open, i, alignment_window_bars) else "new_york_open"
            add_event("impulse_x_session_open", "down", open_bucket)

        # impulse × new_high_low
        if aligned_any(impulse_up, i, alignment_window_bars) and aligned_any(new_high, i, alignment_window_bars):
            add_event("impulse_x_new_high_low", "up", "new_high_20")
        if aligned_any(impulse_down, i, alignment_window_bars) and aligned_any(new_low, i, alignment_window_bars):
            add_event("impulse_x_new_high_low", "down", "new_low_20")

        # compression × session_open
        if aligned_any(compression, i, alignment_window_bars) and (
            aligned_any(london_open, i, alignment_window_bars) or aligned_any(ny_open, i, alignment_window_bars)
        ):
            open_bucket = "london_open" if aligned_any(london_open, i, alignment_window_bars) else "new_york_open"
            add_event("compression_x_session_open", "none", open_bucket)

        # compression × new_high_low
        if aligned_any(compression, i, alignment_window_bars) and aligned_any(new_high, i, alignment_window_bars):
            add_event("compression_x_new_high_low", "up", "new_high_20")
        if aligned_any(compression, i, alignment_window_bars) and aligned_any(new_low, i, alignment_window_bars):
            add_event("compression_x_new_high_low", "down", "new_low_20")

        # compression × prior_day_break
        if aligned_any(compression, i, alignment_window_bars) and aligned_any(prior_up, i, alignment_window_bars):
            add_event("compression_x_prior_day_break", "up", "break_above_prior_day_high")
        if aligned_any(compression, i, alignment_window_bars) and aligned_any(prior_down, i, alignment_window_bars):
            add_event("compression_x_prior_day_break", "down", "break_below_prior_day_low")

        # atr_spike × new_high_low
        if aligned_any(atr_spike, i, alignment_window_bars) and aligned_any(new_high, i, alignment_window_bars):
            add_event("atr_spike_x_new_high_low", "up", "new_high_20")
        if aligned_any(atr_spike, i, alignment_window_bars) and aligned_any(new_low, i, alignment_window_bars):
            add_event("atr_spike_x_new_high_low", "down", "new_low_20")

        # vwap_deviation × session_open
        if aligned_any(vwap_dev_pos, i, alignment_window_bars) and (
            aligned_any(london_open, i, alignment_window_bars) or aligned_any(ny_open, i, alignment_window_bars)
        ):
            open_bucket = "london_open" if aligned_any(london_open, i, alignment_window_bars) else "new_york_open"
            add_event("vwap_deviation_x_session_open", "up", open_bucket)
        if aligned_any(vwap_dev_neg, i, alignment_window_bars) and (
            aligned_any(london_open, i, alignment_window_bars) or aligned_any(ny_open, i, alignment_window_bars)
        ):
            open_bucket = "london_open" if aligned_any(london_open, i, alignment_window_bars) else "new_york_open"
            add_event("vwap_deviation_x_session_open", "down", open_bucket)

        # impulse × vwap_deviation
        if aligned_any(impulse_up, i, alignment_window_bars) and aligned_any(vwap_dev_pos, i, alignment_window_bars):
            add_event("impulse_x_vwap_deviation", "up", "positive_deviation")
        if aligned_any(impulse_down, i, alignment_window_bars) and aligned_any(vwap_dev_neg, i, alignment_window_bars):
            add_event("impulse_x_vwap_deviation", "down", "negative_deviation")

    if not rows:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "combination_name",
                "direction",
                "bucket",
                "session_regime",
                "atr_regime",
                "impulse_size_regime",
                "return_1_bar",
                "return_4_bars",
                "return_8_bars",
                "return_16_bars",
                "adverse_move_4_bars",
                "adverse_move_8_bars",
                "adverse_move_16_bars",
            ]
        )
    return pd.DataFrame(rows)


def compute_edge_score(median_return_4_bars: float, sample_size: int) -> float:
    if sample_size <= 0:
        return float("nan")
    return float(abs(median_return_4_bars) * math.log(sample_size))


def compute_quality_score(median_return_4_bars: float, median_adverse_move_4_bars: float) -> float:
    if median_adverse_move_4_bars <= 0 or not np.isfinite(median_adverse_move_4_bars):
        return float("nan")
    return float(abs(median_return_4_bars) / median_adverse_move_4_bars)


def build_bucket_summary(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(
            columns=[
                "combination_name",
                "direction",
                "bucket",
                "sample_size",
                "median_return_1_bar",
                "median_return_4_bars",
                "median_return_8_bars",
                "median_return_16_bars",
                "p25_return_4_bars",
                "p75_return_4_bars",
                "median_adverse_move_4_bars",
                "median_adverse_move_8_bars",
                "median_adverse_move_16_bars",
                "edge_score",
                "quality_score",
            ]
        )

    summary = (
        events.groupby(["combination_name", "direction", "bucket"], dropna=False)
        .agg(
            sample_size=("timestamp", "count"),
            median_return_1_bar=("return_1_bar", "median"),
            median_return_4_bars=("return_4_bars", "median"),
            median_return_8_bars=("return_8_bars", "median"),
            median_return_16_bars=("return_16_bars", "median"),
            p25_return_4_bars=("return_4_bars", lambda s: float(s.quantile(0.25))),
            p75_return_4_bars=("return_4_bars", lambda s: float(s.quantile(0.75))),
            median_adverse_move_4_bars=("adverse_move_4_bars", "median"),
            median_adverse_move_8_bars=("adverse_move_8_bars", "median"),
            median_adverse_move_16_bars=("adverse_move_16_bars", "median"),
        )
        .reset_index()
    )
    summary["edge_score"] = summary.apply(
        lambda r: compute_edge_score(float(r["median_return_4_bars"]), int(r["sample_size"])),
        axis=1,
    )
    summary["quality_score"] = summary.apply(
        lambda r: compute_quality_score(float(r["median_return_4_bars"]), float(r["median_adverse_move_4_bars"])),
        axis=1,
    )
    return summary.sort_values("edge_score", ascending=False).reset_index(drop=True)


def top_edges(summary: pd.DataFrame, min_sample_size: int, top_n: int = 10) -> pd.DataFrame:
    eligible = summary[summary["sample_size"] >= min_sample_size].copy()
    if eligible.empty:
        return eligible
    return eligible.sort_values("edge_score", ascending=False).head(top_n).reset_index(drop=True)


def build_conditional_edges(
    events: pd.DataFrame,
    summary: pd.DataFrame,
    min_sample_size: int,
) -> pd.DataFrame:
    top10 = top_edges(summary, min_sample_size=min_sample_size, top_n=10)
    if top10.empty:
        return pd.DataFrame(
            columns=[
                "combination_name",
                "direction",
                "bucket",
                "condition_type",
                "condition_value",
                "sample_size",
                "median_return_4_bars",
                "median_adverse_move_4_bars",
                "edge_score",
                "quality_score",
            ]
        )

    rows: list[dict[str, Any]] = []
    for _, top_row in top10.iterrows():
        mask = (
            (events["combination_name"] == top_row["combination_name"])
            & (events["direction"] == top_row["direction"])
            & (events["bucket"] == top_row["bucket"])
        )
        subset = events.loc[mask]
        if subset.empty:
            continue
        for condition_type, allowed_values in {
            "session_regime": {"london_session", "new_york_session"},
            "atr_regime": {"high_atr", "normal_atr"},
            "impulse_size_regime": {"large_impulse", "medium_impulse"},
        }.items():
            grouped = (
                subset.groupby(condition_type)
                .agg(
                    sample_size=("timestamp", "count"),
                    median_return_4_bars=("return_4_bars", "median"),
                    median_adverse_move_4_bars=("adverse_move_4_bars", "median"),
                )
                .reset_index()
            )
            for _, g in grouped.iterrows():
                if str(g[condition_type]) not in allowed_values:
                    continue
                rows.append(
                    {
                        "combination_name": top_row["combination_name"],
                        "direction": top_row["direction"],
                        "bucket": top_row["bucket"],
                        "condition_type": condition_type,
                        "condition_value": str(g[condition_type]),
                        "sample_size": int(g["sample_size"]),
                        "median_return_4_bars": float(g["median_return_4_bars"]),
                        "median_adverse_move_4_bars": float(g["median_adverse_move_4_bars"]),
                        "edge_score": compute_edge_score(float(g["median_return_4_bars"]), int(g["sample_size"])),
                        "quality_score": compute_quality_score(
                            float(g["median_return_4_bars"]),
                            float(g["median_adverse_move_4_bars"]),
                        ),
                    }
                )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values("edge_score", ascending=False).reset_index(drop=True)
    return out


def run_dataset_analysis(
    label: str,
    path: Path,
    output_root: Path,
    alignment_window_bars: int,
    min_sample_size: int,
) -> dict[str, Any]:
    bars = load_bars_any_symbol(path)
    features = build_feature_frame(bars)
    events = detect_pairwise_combinations(features, alignment_window_bars=alignment_window_bars)
    summary = build_bucket_summary(events)
    top = top_edges(summary, min_sample_size=min_sample_size, top_n=15)
    conditional = build_conditional_edges(events, summary, min_sample_size=min_sample_size)

    out_dir = output_root / label
    out_dir.mkdir(parents=True, exist_ok=True)
    events.to_csv(out_dir / "event_combinations_v2.csv", index=False)
    summary.to_csv(out_dir / "combination_bucket_summary_v2.csv", index=False)
    top.to_csv(out_dir / "top_combination_edges_v2.csv", index=False)
    conditional.to_csv(out_dir / "top_conditional_edges_v2.csv", index=False)

    payload = {
        "dataset_label": label,
        "bars_file": str(path),
        "rows": int(len(bars)),
        "events_analyzed": int(len(events)),
        "combinations_detected": int(summary["combination_name"].nunique()) if not summary.empty else 0,
        "top_edges_count": int(len(top)),
        "sample_size_threshold": int(min_sample_size),
    }
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    available, missing = detect_available_datasets()
    dataset_summaries: list[dict[str, Any]] = []

    if not available:
        payload = {"available_datasets": [], "missing_datasets": missing}
        (output_root / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("No datasets detected. Wrote summary.json with missing dataset paths.")
        return

    print("Dataset | events analyzed | combinations detected")
    for label, path in available.items():
        ds_summary = run_dataset_analysis(
            label=label,
            path=path,
            output_root=output_root,
            alignment_window_bars=int(args.alignment_window_bars),
            min_sample_size=int(args.min_sample_size),
        )
        dataset_summaries.append(ds_summary)
        print(
            f"{label:>18} | {ds_summary['events_analyzed']:>14} | "
            f"{ds_summary['combinations_detected']:>21}"
        )

        top_path = output_root / label / "top_combination_edges_v2.csv"
        top_df = pd.read_csv(top_path)
        if not top_df.empty:
            print(f"\nTop edges for {label}:")
            print(
                top_df[
                    [
                        "combination_name",
                        "direction",
                        "bucket",
                        "sample_size",
                        "median_return_4_bars",
                        "edge_score",
                    ]
                ]
                .head(10)
                .to_string(index=False)
            )

    master_summary = {
        "available_datasets": list(available.keys()),
        "missing_datasets": missing,
        "dataset_summaries": dataset_summaries,
        "alignment_rule": f"same bar or within {int(args.alignment_window_bars)} bars",
        "output_root": str(output_root),
    }
    (output_root / "summary.json").write_text(json.dumps(master_summary, indent=2), encoding="utf-8")
    print(f"\nSaved master summary: {output_root / 'summary.json'}")


if __name__ == "__main__":
    main()
