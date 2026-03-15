from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.analytics.ny_impulse import (
    assign_event_volatility_regimes,
    compute_impulse_events,
    summarize_forward_returns,
    summarize_impulse_distribution,
)
from eurusd_quant.data.loaders import load_bars


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze raw NY impulse behavior on EURUSD intraday bars")
    parser.add_argument(
        "--bars",
        default="/Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet",
        help="Path to 15m bars parquet",
    )
    parser.add_argument(
        "--impulse-start-utc",
        default="13:00",
        help="Impulse window start time in UTC",
    )
    parser.add_argument(
        "--impulse-end-utc",
        default="13:30",
        help="Impulse window end time in UTC",
    )
    parser.add_argument(
        "--threshold-pips",
        type=float,
        help="Optional minimum impulse size filter in pips",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/diagnostics/ny_impulse_behavior",
        help="Directory for analysis outputs",
    )
    return parser.parse_args()


def load_execution_config() -> dict:
    with (ROOT / "config" / "execution.yaml").open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    execution_cfg = load_execution_config()
    pip_size = float(execution_cfg["pip_size"])
    bars = load_bars(args.bars)
    events = compute_impulse_events(
        bars,
        impulse_start_utc=args.impulse_start_utc,
        impulse_end_utc=args.impulse_end_utc,
    )
    events, volatility_thresholds = assign_event_volatility_regimes(events)

    if args.threshold_pips is not None:
        events = events.loc[events["impulse_size"] >= (args.threshold_pips * pip_size)].reset_index(drop=True)

    frequency_by_year = (
        events.groupby("year", as_index=False)
        .size()
        .rename(columns={"size": "impulse_count"})
        .sort_values("year")
    )
    frequency_by_month = (
        events.groupby("month", as_index=False)
        .size()
        .rename(columns={"size": "impulse_count"})
        .sort_values("month")
    )

    summary = {
        "bars": args.bars,
        "impulse_window_utc": {
            "start": args.impulse_start_utc,
            "end_exclusive": args.impulse_end_utc,
        },
        "threshold_pips": args.threshold_pips,
        "pip_size": pip_size,
        "distribution": summarize_impulse_distribution(events, pip_size=pip_size),
        "volatility_thresholds": volatility_thresholds,
        "forward_returns": summarize_forward_returns(events, pip_size=pip_size),
        "frequency_by_year": {
            str(int(row.year)): int(row.impulse_count) for row in frequency_by_year.itertuples(index=False)
        },
        "frequency_by_month": {
            str(row.month): int(row.impulse_count) for row in frequency_by_month.itertuples(index=False)
        },
    }

    events_export = events.copy()
    events_export["trade_date"] = events_export["trade_date"].astype(str)
    for column in ("impulse_start_time", "impulse_end_time"):
        events_export[column] = pd.to_datetime(events_export[column], utc=True)

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    events_export.to_csv(output_dir / "impulse_events.csv", index=False)
    frequency_by_year.to_csv(output_dir / "impulse_frequency_by_year.csv", index=False)
    frequency_by_month.to_csv(output_dir / "impulse_frequency_by_month.csv", index=False)

    print(
        f"Analyzed {summary['distribution']['total_impulses']} impulse days; "
        f"median size={summary['distribution']['impulse_size_pips'].get('median', 0.0):.2f} pips"
    )
    for horizon, payload in summary["forward_returns"].items():
        all_bucket = payload["all"]
        print(
            f"+{horizon} bars | mean_return={all_bucket['mean_return_pips']:.3f} pips | "
            f"mean_reversion={all_bucket['mean_reversion_return_pips']:.3f} pips"
        )
    print(f"Saved behavior diagnostics to: {output_dir}")


if __name__ == "__main__":
    main()
