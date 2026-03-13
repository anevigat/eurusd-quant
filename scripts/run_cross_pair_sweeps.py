from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.analytics.metrics import compute_metrics
from eurusd_quant.execution.simulator import ExecutionConfig, ExecutionSimulator
from eurusd_quant.strategies.ny_impulse_mean_reversion import (
    NYImpulseMeanReversionConfig,
    NYImpulseMeanReversionStrategy,
)
from eurusd_quant.utils import infer_pip_size, normalize_symbol, price_to_pips

DEFAULT_CONFIG = "config/cross_pair_sweeps/ny_impulse_cross_pair.yaml"
DEFAULT_OUTPUT_ROOT = "outputs/cross_pair_sweeps"

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


class TupleBar:
    __slots__ = ("_row", "_index_map")

    def __init__(self, row: tuple[Any, ...], index_map: dict[str, int]) -> None:
        self._row = row
        self._index_map = index_map

    def __getitem__(self, key: str) -> Any:
        return self._row[self._index_map[key]]

    def get(self, key: str, default: Any = None) -> Any:
        idx = self._index_map.get(key)
        if idx is None:
            return default
        return self._row[idx]


@dataclass(frozen=True)
class DatasetTask:
    pair: str
    range_label: str
    bars_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run focused NY impulse sweeps across available FX pairs/ranges.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Cross-pair sweep YAML config")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, help="Output root for pair/range sweep results")
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Number of top configs to persist per pair/range",
    )
    parser.add_argument(
        "--min-trades-for-ranking",
        type=int,
        default=100,
        help="Minimum trades for ranking_score eligibility",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_data_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return ROOT / path


def detect_available_datasets(expected_datasets: dict[str, dict[str, str]]) -> tuple[list[DatasetTask], list[dict[str, str]]]:
    available: list[DatasetTask] = []
    missing: list[dict[str, str]] = []

    for pair, ranges in expected_datasets.items():
        for range_label, raw_path in ranges.items():
            resolved = _resolve_data_path(raw_path)
            if resolved.exists():
                available.append(
                    DatasetTask(
                        pair=pair,
                        range_label=range_label,
                        bars_path=resolved,
                    )
                )
            else:
                missing.append(
                    {
                        "pair": pair,
                        "range": range_label,
                        "path": str(resolved),
                        "reason": "missing_bars_file",
                    }
                )

    available.sort(key=lambda x: (x.pair, x.range_label))
    return available, missing


def load_bars_any_symbol(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    missing_cols = [col for col in BAR_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"{path} missing required columns: {missing_cols}")

    bars = df[BAR_COLUMNS].copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    if not bars["timestamp"].is_monotonic_increasing:
        bars = bars.sort_values("timestamp").reset_index(drop=True)
    else:
        bars = bars.reset_index(drop=True)

    if (bars["timeframe"] != "15m").any():
        raise ValueError(f"{path} contains non-15m bars")
    return bars


def infer_dataset_symbol(bars: pd.DataFrame) -> str:
    symbols = bars["symbol"].dropna().astype(str).map(normalize_symbol)
    symbols = symbols[symbols != ""]
    if symbols.empty:
        return "EURUSD"
    unique_symbols = sorted(symbols.unique().tolist())
    if len(unique_symbols) > 1:
        raise ValueError(f"Dataset contains multiple symbols: {unique_symbols}")
    return unique_symbols[0]


def compute_ny_impulse_thresholds(
    bars: pd.DataFrame,
    threshold_percentiles: dict[str, float],
) -> tuple[dict[str, float], int]:
    ts_time = bars["timestamp"].dt.time
    in_window = (ts_time >= time(13, 0)) & (ts_time < time(13, 30))
    window_df = bars.loc[in_window, ["timestamp", "mid_high", "mid_low"]].copy()
    if window_df.empty:
        raise ValueError("No bars found in NY impulse window [13:00, 13:30)")

    window_df["date"] = window_df["timestamp"].dt.date
    daily = (
        window_df.groupby("date", as_index=True)
        .agg(
            impulse_high=("mid_high", "max"),
            impulse_low=("mid_low", "min"),
        )
        .reset_index()
    )
    daily["impulse_size"] = daily["impulse_high"] - daily["impulse_low"]
    if daily["impulse_size"].empty:
        raise ValueError("Unable to compute daily NY impulse sizes")

    thresholds = {
        label: float(daily["impulse_size"].quantile(quantile))
        for label, quantile in threshold_percentiles.items()
    }
    return thresholds, int(len(daily))


def run_once(
    *,
    bar_rows: list[tuple[Any, ...]],
    index_map: dict[str, int],
    strategy_cfg: dict[str, Any],
    execution_cfg: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    strategy = NYImpulseMeanReversionStrategy(NYImpulseMeanReversionConfig.from_dict(strategy_cfg))
    simulator = ExecutionSimulator(ExecutionConfig.from_dict(execution_cfg))

    for row in bar_rows:
        bar = TupleBar(row, index_map)
        simulator.process_bar(bar)
        if simulator.has_open_position():
            position = simulator.get_open_position()
            if position is not None:
                updated = strategy.update_open_position(bar, position)
                if updated is not None:
                    simulator.update_open_position_brackets(*updated)

        order = strategy.generate_order(
            bar,
            has_open_position=simulator.has_open_position(),
            has_pending_order=simulator.has_pending_order(),
        )
        if order is not None:
            simulator.submit_order(order)

    if bar_rows:
        simulator.close_open_position_at_end(TupleBar(bar_rows[-1], index_map))

    trades = simulator.get_trades_df()
    metrics = compute_metrics(trades)
    return trades, metrics


def scoring_profit_factor(value: float) -> float:
    if not math.isfinite(value):
        return 10.0
    return max(0.0, min(value, 10.0))


def build_config_grid(
    *,
    symbol: str,
    threshold_percentiles: dict[str, float],
    threshold_prices: dict[str, float],
    entry_ratios: list[float],
    exit_models: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    for threshold_label, quantile in threshold_percentiles.items():
        threshold_price = float(threshold_prices[threshold_label])
        threshold_pips = float(price_to_pips(symbol, threshold_price))
        for entry_ratio in entry_ratios:
            for exit_label, exit_override in exit_models.items():
                config_id = f"{threshold_label}_entry_{entry_ratio:.2f}_{exit_label}"
                config_record = {
                    "config_id": config_id,
                    "threshold_label": threshold_label,
                    "threshold_quantile": float(quantile),
                    "impulse_threshold_price": threshold_price,
                    "impulse_threshold_pips": threshold_pips,
                    "entry_retracement_ratio": float(entry_ratio),
                    "exit_model_label": exit_label,
                }
                config_record.update(exit_override)
                configs.append(config_record)
    return configs


def run_dataset_sweep(
    *,
    task: DatasetTask,
    strategy_base_cfg: dict[str, Any],
    execution_base_cfg: dict[str, Any],
    threshold_percentiles: dict[str, float],
    entry_ratios: list[float],
    exit_models: dict[str, dict[str, Any]],
    min_trades_for_ranking: int,
    top_k: int,
    output_root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    bars = load_bars_any_symbol(task.bars_path)
    symbol = infer_dataset_symbol(bars)
    threshold_prices, impulse_days = compute_ny_impulse_thresholds(bars, threshold_percentiles)
    config_grid = build_config_grid(
        symbol=symbol,
        threshold_percentiles=threshold_percentiles,
        threshold_prices=threshold_prices,
        entry_ratios=entry_ratios,
        exit_models=exit_models,
    )

    execution_cfg = dict(execution_base_cfg)
    # Keep pips/slippage semantics correct for JPY vs non-JPY symbols.
    execution_cfg["pip_size"] = float(infer_pip_size(symbol))

    columns = bars.columns.tolist()
    index_map = {name: idx for idx, name in enumerate(columns)}
    bar_rows = list(bars.itertuples(index=False, name=None))
    total_days = int(bars["timestamp"].dt.date.nunique())

    rows: list[dict[str, Any]] = []
    for config in config_grid:
        strategy_cfg = dict(strategy_base_cfg)
        strategy_cfg["impulse_threshold_pips"] = float(config["impulse_threshold_pips"])
        strategy_cfg["retracement_entry_ratio"] = float(config["entry_retracement_ratio"])
        strategy_cfg["exit_model"] = str(config["exit_model"])
        if "atr_target_multiple" in config:
            strategy_cfg["atr_target_multiple"] = float(config["atr_target_multiple"])
        if "retracement_target_ratio" in config:
            strategy_cfg["retracement_target_ratio"] = float(config["retracement_target_ratio"])

        _, metrics = run_once(
            bar_rows=bar_rows,
            index_map=index_map,
            strategy_cfg=strategy_cfg,
            execution_cfg=execution_cfg,
        )
        pf = float(metrics["profit_factor"])
        score_raw = float(scoring_profit_factor(pf) * math.log(int(metrics["total_trades"]) + 1))
        score_rank = score_raw if int(metrics["total_trades"]) >= min_trades_for_ranking else float("nan")
        rows.append(
            {
                "pair": task.pair,
                "range_label": task.range_label,
                "symbol": symbol,
                "config_id": config["config_id"],
                "threshold_label": config["threshold_label"],
                "threshold_quantile": config["threshold_quantile"],
                "impulse_threshold_price": config["impulse_threshold_price"],
                "impulse_threshold_pips": config["impulse_threshold_pips"],
                "entry_retracement_ratio": config["entry_retracement_ratio"],
                "exit_model_label": config["exit_model_label"],
                "exit_model": config["exit_model"],
                "atr_target_multiple": config.get("atr_target_multiple", np.nan),
                "retracement_target_ratio": config.get("retracement_target_ratio", np.nan),
                "total_trades": int(metrics["total_trades"]),
                "win_rate": float(metrics["win_rate"]),
                "net_pnl": float(metrics["net_pnl"]),
                "profit_factor": pf,
                "expectancy": float(metrics["expectancy"]),
                "max_drawdown": float(metrics["max_drawdown"]),
                "avg_win_pips": float(price_to_pips(symbol, metrics["average_win"])),
                "avg_loss_pips": float(price_to_pips(symbol, metrics["average_loss"])),
                "score_raw": score_raw,
                "ranking_score": score_rank,
            }
        )

    results = pd.DataFrame(rows).sort_values(["ranking_score", "score_raw"], ascending=False, na_position="last")
    if results["ranking_score"].notna().any():
        best_row = results.loc[results["ranking_score"].idxmax()]
    else:
        best_row = results.loc[results["score_raw"].idxmax()]

    top_configs = results.head(top_k).reset_index(drop=True)

    out_dir = output_root / task.pair.lower() / task.range_label
    out_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(out_dir / "experiment_results.csv", index=False)
    top_configs.to_csv(out_dir / "top_configs.csv", index=False)

    summary = {
        "pair": task.pair,
        "range_label": task.range_label,
        "symbol": symbol,
        "bars_file": str(task.bars_path),
        "bars_count": int(len(bars)),
        "total_days": total_days,
        "ny_impulse_days": impulse_days,
        "total_configs": int(len(config_grid)),
        "top_config": {
            "config_id": str(best_row["config_id"]),
            "profit_factor": float(best_row["profit_factor"]),
            "total_trades": int(best_row["total_trades"]),
            "net_pnl": float(best_row["net_pnl"]),
            "ranking_score": (
                None if pd.isna(best_row["ranking_score"]) else float(best_row["ranking_score"])
            ),
        },
        "threshold_prices": {k: float(v) for k, v in threshold_prices.items()},
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return results, top_configs, summary


def main() -> None:
    args = parse_args()
    output_root = _resolve_data_path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    cfg = load_yaml(_resolve_data_path(args.config))
    strategy_key = str(cfg.get("strategy", "ny_impulse_mean_reversion"))
    if strategy_key != "ny_impulse_mean_reversion":
        raise ValueError("This batch runner currently supports only ny_impulse_mean_reversion")

    expected_datasets = dict(cfg["expected_datasets"])
    threshold_percentiles = {k: float(v) for k, v in dict(cfg["threshold_percentiles"]).items()}
    entry_ratios = [float(x) for x in cfg["entry_retracement_ratios"]]
    exit_models = {str(k): dict(v) for k, v in dict(cfg["exit_models"]).items()}

    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    if strategy_key not in strategy_cfg_all:
        raise ValueError(f"Missing strategy config block: {strategy_key}")
    strategy_base_cfg = dict(strategy_cfg_all[strategy_key])
    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")

    tasks, missing = detect_available_datasets(expected_datasets)
    processed_summaries: list[dict[str, Any]] = []
    generated_paths: list[str] = []

    if not tasks:
        summary = {
            "strategy": strategy_key,
            "processed_datasets": [],
            "missing_datasets": missing,
            "note": "No available pair/range datasets were found.",
        }
        with (output_root / "summary.json").open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print("No available datasets found. Wrote summary with missing-file details.")
        return

    print("pair | range | best_config | PF | trades | net_pnl")
    for task in tasks:
        results, _, dataset_summary = run_dataset_sweep(
            task=task,
            strategy_base_cfg=strategy_base_cfg,
            execution_base_cfg=execution_cfg,
            threshold_percentiles=threshold_percentiles,
            entry_ratios=entry_ratios,
            exit_models=exit_models,
            min_trades_for_ranking=int(args.min_trades_for_ranking),
            top_k=int(args.top_k),
            output_root=output_root,
        )
        processed_summaries.append(dataset_summary)
        generated_paths.append(str(output_root / task.pair.lower() / task.range_label))
        best = dataset_summary["top_config"]
        print(
            f"{task.pair:>6} | {task.range_label:>10} | {best['config_id']} | "
            f"{best['profit_factor']:.4f} | {best['total_trades']:>6} | {best['net_pnl']:.6f}"
        )

    summary = {
        "strategy": strategy_key,
        "sweep_dimensions": {
            "threshold_labels": list(threshold_percentiles.keys()),
            "entry_retracement_ratios": entry_ratios,
            "exit_models": list(exit_models.keys()),
            "total_configs_per_dataset": len(threshold_percentiles) * len(entry_ratios) * len(exit_models),
        },
        "processed_datasets": processed_summaries,
        "missing_datasets": missing,
        "generated_paths": generated_paths,
    }
    with (output_root / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved cross-pair sweep summary: {output_root / 'summary.json'}")


if __name__ == "__main__":
    main()
