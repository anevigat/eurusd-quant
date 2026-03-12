import argparse
import itertools
import json
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
from eurusd_quant.data.loaders import load_bars
from eurusd_quant.data.sessions import in_time_window, parse_hhmm
from eurusd_quant.execution.models import Order
from eurusd_quant.execution.simulator import ExecutionConfig, ExecutionSimulator
from eurusd_quant.strategies.base import BaseStrategy
from eurusd_quant.utils import normalize_symbol

DEFAULT_BARS = "data/bars/15m/eurusd_bars_15m_2018_2024.parquet"
DEFAULT_OUTPUT_DIR = "outputs/event_strategy_sweeps"

PARAM_SPACE: dict[str, list[Any]] = {
    "impulse_bars": [1, 2, 3, 4],
    "impulse_threshold_atr": [0.8, 1.0, 1.2, 1.5],
    "entry_delay_bars": [0, 1, 2],
    "session_filter": ["none", "london", "new_york"],
    "stop_atr": [0.8, 1.0, 1.2],
    "target_atr": [0.8, 1.0, 1.2],
    "max_hold_bars": [4, 6, 8],
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

SESSION_WINDOWS: dict[str, tuple[time, time]] = {
    "london": (parse_hhmm("07:00"), parse_hhmm("12:00")),
    "new_york": (parse_hhmm("13:00"), parse_hhmm("17:00")),
}


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
class ImpulseReversionTemplateConfig:
    timeframe: str
    atr_period: int
    impulse_bars: int
    impulse_threshold_atr: float
    entry_delay_bars: int
    session_filter: str
    stop_atr: float
    target_atr: float
    max_hold_bars: int


class ImpulseReversionTemplateStrategy(BaseStrategy):
    DEFAULT_SYMBOL = "EURUSD"

    def __init__(self, config: ImpulseReversionTemplateConfig) -> None:
        self.config = config
        if config.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if config.impulse_bars < 1:
            raise ValueError("impulse_bars must be >= 1")
        if config.impulse_threshold_atr <= 0:
            raise ValueError("impulse_threshold_atr must be > 0")
        if config.entry_delay_bars < 0:
            raise ValueError("entry_delay_bars must be >= 0")
        if config.session_filter not in {"none", "london", "new_york"}:
            raise ValueError("session_filter must be one of: none, london, new_york")
        if config.stop_atr <= 0:
            raise ValueError("stop_atr must be > 0")
        if config.target_atr <= 0:
            raise ValueError("target_atr must be > 0")
        if config.max_hold_bars < 1:
            raise ValueError("max_hold_bars must be >= 1")

        self._prev_mid_close: float | None = None
        self._tr_values: list[float] = []
        self._atr: float | None = None
        self._close_values: list[float] = []
        self._pending_side: str | None = None
        self._pending_bars_remaining: int = 0

    def _extract_symbol(self, bar: pd.Series) -> str:
        if hasattr(bar, "get"):
            raw_symbol = bar.get("symbol", self.DEFAULT_SYMBOL)
        else:
            try:
                raw_symbol = bar["symbol"]
            except (KeyError, TypeError):
                raw_symbol = self.DEFAULT_SYMBOL
        if pd.isna(raw_symbol):
            return self.DEFAULT_SYMBOL
        normalized = normalize_symbol(str(raw_symbol))
        if not normalized:
            return self.DEFAULT_SYMBOL
        return normalized

    def _update_atr(self, bar: pd.Series) -> float:
        mid_high = float(bar["mid_high"])
        mid_low = float(bar["mid_low"])
        mid_close = float(bar["mid_close"])
        if self._prev_mid_close is None:
            tr = mid_high - mid_low
        else:
            tr = max(
                mid_high - mid_low,
                abs(mid_high - self._prev_mid_close),
                abs(mid_low - self._prev_mid_close),
            )
        self._tr_values.append(tr)
        if len(self._tr_values) > self.config.atr_period:
            self._tr_values.pop(0)
        self._prev_mid_close = mid_close
        self._atr = float(np.mean(self._tr_values))
        return self._atr

    def _in_session_filter(self, timestamp: pd.Timestamp) -> bool:
        if self.config.session_filter == "none":
            return True
        start, end = SESSION_WINDOWS[self.config.session_filter]
        return in_time_window(timestamp, start, end)

    def _try_emit_delayed_order(self, bar: pd.Series) -> Order | None:
        if self._pending_side is None:
            return None
        if self._pending_bars_remaining > 0:
            self._pending_bars_remaining -= 1
            return None
        if self._atr is None or self._atr <= 0:
            return None

        side = self._pending_side
        self._pending_side = None

        symbol = self._extract_symbol(bar)
        stop_distance = self._atr * self.config.stop_atr
        target_distance = self._atr * self.config.target_atr
        timestamp = bar["timestamp"]

        if side == "long":
            entry_reference = float(bar["ask_close"])
            return Order(
                symbol=symbol,
                timeframe=self.config.timeframe,
                side="long",
                signal_time=timestamp,
                entry_reference=entry_reference,
                stop_loss=entry_reference - stop_distance,
                take_profit=entry_reference + target_distance,
                max_holding_bars=self.config.max_hold_bars,
            )

        entry_reference = float(bar["bid_close"])
        return Order(
            symbol=symbol,
            timeframe=self.config.timeframe,
            side="short",
            signal_time=timestamp,
            entry_reference=entry_reference,
            stop_loss=entry_reference + stop_distance,
            take_profit=entry_reference - target_distance,
            max_holding_bars=self.config.max_hold_bars,
        )

    def generate_order(
        self,
        bar: pd.Series,
        has_open_position: bool,
        has_pending_order: bool,
    ) -> Order | None:
        timestamp: pd.Timestamp = bar["timestamp"]
        mid_close = float(bar["mid_close"])
        atr = self._update_atr(bar)
        self._close_values.append(mid_close)

        if has_open_position or has_pending_order:
            return None

        delayed_order = self._try_emit_delayed_order(bar)
        if delayed_order is not None:
            return delayed_order

        if len(self._close_values) <= self.config.impulse_bars:
            return None
        if atr <= 0:
            return None
        if not self._in_session_filter(timestamp):
            return None
        if self._pending_side is not None:
            return None

        ref_close = self._close_values[-(self.config.impulse_bars + 1)]
        impulse_move = mid_close - ref_close
        impulse_strength_atr = abs(impulse_move) / atr
        if impulse_strength_atr < self.config.impulse_threshold_atr:
            return None

        self._pending_side = "short" if impulse_move > 0 else "long"
        self._pending_bars_remaining = self.config.entry_delay_bars
        return self._try_emit_delayed_order(bar)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run parameter sweeps for event-driven strategy templates.")
    parser.add_argument("--bars", default=DEFAULT_BARS, help="Input bars parquet path")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory root")
    parser.add_argument(
        "--max-configs",
        type=int,
        default=360,
        help="Max configs to execute from full grid (<=0 means run full grid)",
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=100,
        help="Minimum trades required for ranked configs",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_grid(param_space: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = list(param_space.keys())
    combos = itertools.product(*(param_space[k] for k in keys))
    return [dict(zip(keys, vals)) for vals in combos]


def select_configs(configs: list[dict[str, Any]], max_configs: int) -> list[dict[str, Any]]:
    if max_configs <= 0 or max_configs >= len(configs):
        return list(configs)
    indices = np.linspace(0, len(configs) - 1, num=max_configs, dtype=int)
    unique_indices = sorted(set(int(i) for i in indices))
    return [configs[i] for i in unique_indices]


def run_single_config(
    bar_rows: list[tuple[Any, ...]],
    index_map: dict[str, int],
    execution_cfg: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    strategy_cfg = ImpulseReversionTemplateConfig(
        timeframe="15m",
        atr_period=14,
        impulse_bars=int(cfg["impulse_bars"]),
        impulse_threshold_atr=float(cfg["impulse_threshold_atr"]),
        entry_delay_bars=int(cfg["entry_delay_bars"]),
        session_filter=str(cfg["session_filter"]),
        stop_atr=float(cfg["stop_atr"]),
        target_atr=float(cfg["target_atr"]),
        max_hold_bars=int(cfg["max_hold_bars"]),
    )
    strategy = ImpulseReversionTemplateStrategy(strategy_cfg)
    simulator = ExecutionSimulator(ExecutionConfig.from_dict(execution_cfg))
    last_bar: TupleBar | None = None

    for row in bar_rows:
        bar = TupleBar(row, index_map)
        last_bar = bar
        simulator.process_bar(bar)
        order = strategy.generate_order(
            bar,
            has_open_position=simulator.has_open_position(),
            has_pending_order=simulator.has_pending_order(),
        )
        if order is not None:
            simulator.submit_order(order)

    if last_bar is not None:
        simulator.close_open_position_at_end(last_bar)

    metrics = compute_metrics(simulator.get_trades_df())
    return {
        "total_trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "net_pnl": float(metrics["net_pnl"]),
        "profit_factor": float(metrics["profit_factor"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "expectancy": float(metrics["expectancy"]),
    }


def add_ranking(results: pd.DataFrame, min_trades: int) -> pd.DataFrame:
    out = results.copy()
    out["score"] = np.nan
    mask = out["total_trades"] >= min_trades
    out.loc[mask, "score"] = out.loc[mask, "profit_factor"] * np.log(out.loc[mask, "total_trades"])
    out.loc[~np.isfinite(out["score"]), "score"] = np.nan
    return out


def build_summary(
    bars_path: str,
    output_dir: str,
    total_grid_configs: int,
    executed_configs: int,
    min_trades: int,
    ranked: pd.DataFrame,
    top_configs: pd.DataFrame,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "bars": bars_path,
        "output_dir": output_dir,
        "template": "impulse_reversion",
        "total_grid_configs": int(total_grid_configs),
        "executed_configs": int(executed_configs),
        "min_trades_for_ranking": int(min_trades),
        "ranked_config_count": int(ranked["score"].notna().sum()),
    }
    if not top_configs.empty:
        summary["best_config"] = top_configs.iloc[0].to_dict()
    return summary


def run_sweep(
    bars_path: str,
    output_dir: str,
    max_configs: int,
    min_trades: int,
    param_space: dict[str, list[Any]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    bars = load_bars(bars_path)
    if bars.empty:
        raise ValueError("Input bars dataset is empty.")

    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    bar_rows = [tuple(row) for row in bars[BAR_COLUMNS].itertuples(index=False, name=None)]
    index_map = {col: idx for idx, col in enumerate(BAR_COLUMNS)}
    params = PARAM_SPACE if param_space is None else param_space
    full_grid = generate_grid(params)
    selected_grid = select_configs(full_grid, max_configs=max_configs)

    rows: list[dict[str, Any]] = []
    for idx, cfg in enumerate(selected_grid, start=1):
        metrics = run_single_config(
            bar_rows=bar_rows,
            index_map=index_map,
            execution_cfg=execution_cfg,
            cfg=cfg,
        )
        rows.append({"config_id": f"cfg_{idx:04d}", **cfg, **metrics})
        if idx % 25 == 0 or idx == len(selected_grid):
            print(f"[progress] completed {idx}/{len(selected_grid)} configs")

    results = pd.DataFrame(rows)
    ranked = add_ranking(results, min_trades=min_trades)
    top_configs = (
        ranked[ranked["score"].notna()]
        .sort_values("score", ascending=False)
        .head(20)
        .reset_index(drop=True)
    )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "experiment_results.csv"
    top_path = out_dir / "top_configs.csv"
    summary_path = out_dir / "summary.json"

    ranked.to_csv(results_path, index=False)
    top_configs.to_csv(top_path, index=False)
    summary = build_summary(
        bars_path=bars_path,
        output_dir=output_dir,
        total_grid_configs=len(full_grid),
        executed_configs=len(selected_grid),
        min_trades=min_trades,
        ranked=ranked,
        top_configs=top_configs,
    )
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return ranked, top_configs, summary


def print_top10(top_configs: pd.DataFrame) -> None:
    print("config_id | PF | trades | net_pnl | parameters")
    if top_configs.empty:
        print("no ranked configs passed the trade-count filter")
        return
    for _, row in top_configs.head(10).iterrows():
        params = (
            f"impulse_bars={int(row['impulse_bars'])}, "
            f"thr={float(row['impulse_threshold_atr'])}, "
            f"delay={int(row['entry_delay_bars'])}, "
            f"session={row['session_filter']}, "
            f"stop={float(row['stop_atr'])}, "
            f"target={float(row['target_atr'])}, "
            f"hold={int(row['max_hold_bars'])}"
        )
        print(
            f"{row['config_id']} | {float(row['profit_factor']):.4f} | "
            f"{int(row['total_trades'])} | {float(row['net_pnl']):.6f} | {params}"
        )


def main() -> None:
    args = parse_args()
    _ranked, top_configs, summary = run_sweep(
        bars_path=args.bars,
        output_dir=args.output_dir,
        max_configs=args.max_configs,
        min_trades=args.min_trades,
    )
    print_top10(top_configs)
    print("\nSaved outputs:")
    print(f"- {Path(args.output_dir) / 'experiment_results.csv'}")
    print(f"- {Path(args.output_dir) / 'top_configs.csv'}")
    print(f"- {Path(args.output_dir) / 'summary.json'}")
    print(
        f"\nExecuted configs: {summary['executed_configs']} / "
        f"full grid {summary['total_grid_configs']}"
    )
    print(f"Ranked configs (trades >= {args.min_trades}): {summary['ranked_config_count']}")


if __name__ == "__main__":
    main()
