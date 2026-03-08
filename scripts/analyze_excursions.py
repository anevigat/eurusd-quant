from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze MFE/MAE excursions for breakout trades")
    parser.add_argument("--bars", required=True, help="Path to bars parquet")
    parser.add_argument("--trades", required=True, help="Path to trades parquet")
    parser.add_argument("--output-dir", default="outputs/excursions", help="Directory for excursion outputs")
    parser.add_argument("--pip-size", type=float, default=None, help="Optional pip size override")
    return parser.parse_args()


def load_pip_size(explicit: float | None) -> float:
    if explicit is not None:
        return explicit
    execution_cfg_path = ROOT / "config" / "execution.yaml"
    with execution_cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return float(cfg["pip_size"])


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pip_size = load_pip_size(args.pip_size)

    bars = pd.read_parquet(args.bars, columns=["timestamp", "bid_low", "bid_high", "ask_low", "ask_high"]).copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)

    trades = pd.read_parquet(args.trades).copy()
    if trades.empty:
        raise ValueError("Trades parquet is empty; cannot compute excursions")
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)

    mfe_rows: list[dict] = []
    mae_rows: list[dict] = []

    for idx, trade in trades.reset_index(drop=True).iterrows():
        entry_time = trade["entry_time"]
        exit_time = trade["exit_time"]
        side = trade["side"]
        entry_price = float(trade["entry_price"])

        trade_bars = bars[(bars["timestamp"] >= entry_time) & (bars["timestamp"] <= exit_time)]
        if trade_bars.empty:
            continue

        if side == "long":
            mae_pips = (entry_price - float(trade_bars["bid_low"].min())) / pip_size
            mfe_pips = (float(trade_bars["bid_high"].max()) - entry_price) / pip_size
        elif side == "short":
            mae_pips = (float(trade_bars["ask_high"].max()) - entry_price) / pip_size
            mfe_pips = (entry_price - float(trade_bars["ask_low"].min())) / pip_size
        else:
            continue

        base_row = {
            "trade_id": int(idx),
            "side": side,
            "entry_time": entry_time.isoformat(),
            "exit_time": exit_time.isoformat(),
        }
        mfe_rows.append({**base_row, "mfe_pips": float(mfe_pips)})
        mae_rows.append({**base_row, "mae_pips": float(mae_pips)})

    mfe_df = pd.DataFrame(mfe_rows)
    mae_df = pd.DataFrame(mae_rows)
    if mfe_df.empty or mae_df.empty:
        raise RuntimeError("No excursion rows computed from bars/trades overlap")

    mfe_df.to_csv(output_dir / "mfe_distribution.csv", index=False)
    mae_df.to_csv(output_dir / "mae_distribution.csv", index=False)

    median_mfe = float(mfe_df["mfe_pips"].median())
    median_mae = float(mae_df["mae_pips"].median())
    mean_mfe = float(mfe_df["mfe_pips"].mean())
    mean_mae = float(mae_df["mae_pips"].mean())
    mfe_95 = float(np.percentile(mfe_df["mfe_pips"], 95))
    mae_95 = float(np.percentile(mae_df["mae_pips"], 95))

    ratio = median_mfe / abs(median_mae) if median_mae != 0 else float("inf")
    interpretation = "breakout potential exists" if ratio > 1.5 else "breakout structure likely weak"

    summary = {
        "trades_analyzed": int(len(mfe_df)),
        "median_mae_pips": median_mae,
        "median_mfe_pips": median_mfe,
        "mean_mae_pips": mean_mae,
        "mean_mfe_pips": mean_mfe,
        "p95_mfe_pips": mfe_95,
        "p95_mae_pips": mae_95,
        "ratio_median_mfe_to_median_mae_abs": ratio,
        "interpretation": interpretation,
    }

    with (output_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("Excursion analysis complete")
    print(f"trades_analyzed: {summary['trades_analyzed']}")
    print(f"median_mae_pips: {summary['median_mae_pips']}")
    print(f"median_mfe_pips: {summary['median_mfe_pips']}")
    print(f"mean_mae_pips: {summary['mean_mae_pips']}")
    print(f"mean_mfe_pips: {summary['mean_mfe_pips']}")
    print(f"p95_mfe_pips: {summary['p95_mfe_pips']}")
    print(f"p95_mae_pips: {summary['p95_mae_pips']}")
    print(f"ratio: {summary['ratio_median_mfe_to_median_mae_abs']}")
    print(f"interpretation: {summary['interpretation']}")
    print(f"mfe_distribution: {output_dir / 'mfe_distribution.csv'}")
    print(f"mae_distribution: {output_dir / 'mae_distribution.csv'}")


if __name__ == "__main__":
    main()
