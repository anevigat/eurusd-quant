from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.backtest import run_backtest
from eurusd_quant.data.loaders import load_bars


DEFAULT_BARS = "data/bars/1d/eurusd_bars_1d_2018_2024.parquet"
DEFAULT_OUTPUT_ROOT = "outputs/trend_sweeps"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run small hypothesis-driven sweeps for FX trend strategies.")
    parser.add_argument(
        "--strategy",
        required=True,
        choices=["tsmom_ma_cross", "tsmom_donchian", "tsmom_return_sign"],
        help="Trend strategy to sweep",
    )
    parser.add_argument("--bars", default=DEFAULT_BARS, help="Input bars parquet")
    parser.add_argument("--output-dir", help="Optional explicit output directory")
    parser.add_argument("--top-k", type=int, default=10, help="Number of top configs to save")
    return parser.parse_args()


def _grid_for_strategy(strategy_name: str) -> list[dict[str, Any]]:
    common = {
        "timeframe": "1d",
        "atr_period": 14,
        "max_holding_bars": 252,
    }
    atr_stop_values: list[float | None] = [None, 1.5, 2.0]
    trailing_values = [False, True]

    if strategy_name == "tsmom_ma_cross":
        configs = []
        for fast_window, slow_window, atr_stop_multiple, trailing_stop in itertools.product(
            [10, 20, 50],
            [50, 100, 200],
            atr_stop_values,
            trailing_values,
        ):
            if slow_window <= fast_window:
                continue
            if trailing_stop and atr_stop_multiple is None:
                continue
            configs.append(
                {
                    **common,
                    "fast_window": fast_window,
                    "slow_window": slow_window,
                    "atr_stop_multiple": atr_stop_multiple,
                    "trailing_stop": trailing_stop,
                }
            )
        return configs

    if strategy_name == "tsmom_donchian":
        return [
            {
                **common,
                "breakout_window": breakout_window,
                "atr_stop_multiple": atr_stop_multiple,
                "trailing_stop": trailing_stop,
            }
            for breakout_window, atr_stop_multiple, trailing_stop in itertools.product(
                [20, 55, 100],
                atr_stop_values,
                trailing_values,
            )
            if not (trailing_stop and atr_stop_multiple is None)
        ]

    return [
        {
            **common,
            "lookback_window": lookback_window,
            "return_threshold": return_threshold,
            "atr_stop_multiple": atr_stop_multiple,
            "trailing_stop": trailing_stop,
        }
        for lookback_window, return_threshold, atr_stop_multiple, trailing_stop in itertools.product(
            [20, 60, 120],
            [0.0, 0.005],
            atr_stop_values,
            trailing_values,
        )
        if not (trailing_stop and atr_stop_multiple is None)
    ]


def _score(metrics: dict[str, Any]) -> float:
    if int(metrics["total_trades"]) == 0:
        return float("-inf")
    profit_factor = float(metrics["profit_factor"])
    if not math.isfinite(profit_factor):
        profit_factor = 10.0
    return float(min(profit_factor, 10.0) * math.log(int(metrics["total_trades"]) + 1))


def main() -> None:
    args = parse_args()
    bars = load_bars(args.bars)
    execution_config = yaml.safe_load((ROOT / "config" / "execution.yaml").read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir or (Path(DEFAULT_OUTPUT_ROOT) / args.strategy))
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for config in _grid_for_strategy(args.strategy):
        result = run_backtest(bars, args.strategy, config, execution_config)
        rows.append(
            {
                "strategy": args.strategy,
                "config_json": json.dumps(config, sort_keys=True),
                "score": _score(result.metrics),
                **result.metrics,
            }
        )

    results_df = pd.DataFrame(rows).sort_values(
        ["score", "profit_factor", "net_pnl", "expectancy"],
        ascending=[False, False, False, False],
    )
    top_configs_df = results_df.head(args.top_k).reset_index(drop=True)

    results_df.to_csv(output_dir / "experiment_results.csv", index=False)
    top_configs_df.to_csv(output_dir / "top_configs.csv", index=False)
    summary = {
        "strategy": args.strategy,
        "bars": args.bars,
        "total_configs": int(len(results_df)),
        "top_k": int(args.top_k),
        "best_config": json.loads(top_configs_df.iloc[0]["config_json"]) if not top_configs_df.empty else None,
        "best_metrics": top_configs_df.iloc[0][
            ["total_trades", "profit_factor", "net_pnl", "expectancy", "max_drawdown"]
        ].to_dict()
        if not top_configs_df.empty
        else None,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Saved sweep results to: {output_dir}")
    print(f"Configs evaluated: {len(results_df)}")


if __name__ == "__main__":
    main()
