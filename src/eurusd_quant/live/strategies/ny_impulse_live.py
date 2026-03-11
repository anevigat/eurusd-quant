from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from eurusd_quant.data.sessions import in_time_window, parse_hhmm
from eurusd_quant.live.base_strategy import LiveStrategy
from eurusd_quant.strategies.ny_impulse_mean_reversion import (
    NYImpulseMeanReversionConfig,
    NYImpulseMeanReversionStrategy,
)
from eurusd_quant.utils import pips_to_price

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_P90_THRESHOLD_PRICE = 0.002455


class NYImpulseLiveStrategy(LiveStrategy):
    def __init__(self, p90_price_threshold: float = DEFAULT_P90_THRESHOLD_PRICE) -> None:
        with (ROOT / "config" / "execution.yaml").open("r", encoding="utf-8") as f:
            execution_cfg = yaml.safe_load(f)
        with (ROOT / "config" / "strategies.yaml").open("r", encoding="utf-8") as f:
            strategy_cfg_all = yaml.safe_load(f)

        if "ny_impulse_mean_reversion" not in strategy_cfg_all:
            raise ValueError("Strategy config 'ny_impulse_mean_reversion' not found")

        pip_size = float(execution_cfg["pip_size"])
        threshold_pips = float(p90_price_threshold) / pip_size

        # Frozen validated configuration.
        cfg = dict(strategy_cfg_all["ny_impulse_mean_reversion"])
        cfg["impulse_threshold_pips"] = threshold_pips
        cfg["retracement_entry_ratio"] = 0.50
        cfg["exit_model"] = "atr"
        cfg["atr_target_multiple"] = 1.0

        self._config = NYImpulseMeanReversionConfig.from_dict(cfg)
        self._impulse_start = cfg["impulse_start_utc"]
        self._impulse_end = cfg["impulse_end_utc"]

    def name(self) -> str:
        return "ny_impulse_mean_reversion"

    def evaluate_latest(self, bars: pd.DataFrame) -> dict | None:
        if bars.empty:
            return None

        strategy = NYImpulseMeanReversionStrategy(self._config)
        latest_ts = pd.to_datetime(bars["timestamp"].iloc[-1], utc=True)
        today_bars = bars[pd.to_datetime(bars["timestamp"], utc=True).dt.date == latest_ts.date()].copy()

        latest_order = None
        for _, bar in today_bars.iterrows():
            order = strategy.generate_order(bar, has_open_position=False, has_pending_order=False)
            if pd.to_datetime(bar["timestamp"], utc=True) == latest_ts:
                latest_order = order

        if latest_order is None:
            return None

        impulse_size = self._compute_impulse_size(today_bars)
        impulse_threshold = float(pips_to_price(latest_order.symbol, self._config.impulse_threshold_pips))

        return {
            "timestamp": latest_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "strategy": self.name(),
            "symbol": latest_order.symbol,
            "side": latest_order.side,
            "entry_price": float(latest_order.entry_reference),
            "stop_price": float(latest_order.stop_loss),
            "target_price": float(latest_order.take_profit),
            "impulse_size": float(impulse_size),
            "impulse_threshold": impulse_threshold,
        }

    def _compute_impulse_size(self, today_bars: pd.DataFrame) -> float:
        start_t = parse_hhmm(self._impulse_start)
        end_t = parse_hhmm(self._impulse_end)
        mask = today_bars["timestamp"].apply(
            lambda t: in_time_window(pd.to_datetime(t, utc=True), start_t, end_t)
        )
        impulse_bars = today_bars[mask]
        if impulse_bars.empty:
            return 0.0
        return float(impulse_bars["mid_high"].max() - impulse_bars["mid_low"].min())
