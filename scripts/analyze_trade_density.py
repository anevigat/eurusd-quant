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

from eurusd_quant.analytics.ny_impulse import summarize_trade_density


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze trade density and yearly concentration for one strategy")
    parser.add_argument("--trades", required=True, help="Path to trades parquet")
    parser.add_argument(
        "--output-dir",
        default="outputs/diagnostics/ny_impulse_trade_density",
        help="Directory for trade-density outputs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades = pd.read_parquet(args.trades)
    summary, yearly, monthly, signal_windows, zero_trade_months = summarize_trade_density(trades)
    summary["trades_path"] = args.trades

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    yearly.to_csv(output_dir / "trades_by_year.csv", index=False)
    monthly.to_csv(output_dir / "trades_by_month.csv", index=False)
    signal_windows.to_csv(output_dir / "trades_by_signal_window.csv", index=False)
    zero_trade_months.to_csv(output_dir / "zero_trade_months.csv", index=False)

    print(
        f"Trades={summary['total_trades']} | dominant_year_share={summary['dominant_year_pnl_share']:.4f} | "
        f"zero_trade_months={summary['zero_trade_month_count']}"
    )
    print(f"Saved trade-density diagnostics to: {output_dir}")


if __name__ == "__main__":
    main()
