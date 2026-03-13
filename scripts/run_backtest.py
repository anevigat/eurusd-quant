from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eurusd_quant.analytics.metrics import compute_metrics
from eurusd_quant.data.loaders import load_bars
from eurusd_quant.execution.simulator import ExecutionConfig, ExecutionSimulator
from eurusd_quant.strategies.asian_range_compression_breakout import (
    AsianRangeCompressionBreakoutConfig,
    AsianRangeCompressionBreakoutStrategy,
)
from eurusd_quant.strategies.compression_breakout import (
    CompressionBreakoutConfig,
    CompressionBreakoutStrategy,
)
from eurusd_quant.strategies.compression_breakout_continuation import (
    CompressionBreakoutContinuationConfig,
    CompressionBreakoutContinuationStrategy,
)
from eurusd_quant.strategies.false_breakout_reversal import (
    FalseBreakoutReversalConfig,
    FalseBreakoutReversalStrategy,
)
from eurusd_quant.strategies.head_shoulders_reversal import (
    HeadShouldersReversalConfig,
    HeadShouldersReversalStrategy,
)
from eurusd_quant.strategies.impulse_session_open import (
    ImpulseSessionOpenConfig,
    ImpulseSessionOpenStrategy,
)
from eurusd_quant.strategies.london_pullback_continuation import (
    LondonPullbackContinuationConfig,
    LondonPullbackContinuationStrategy,
)
from eurusd_quant.strategies.london_open_impulse_fade import (
    LondonOpenImpulseFadeConfig,
    LondonOpenImpulseFadeStrategy,
)
from eurusd_quant.strategies.ny_impulse_mean_reversion import (
    NYImpulseMeanReversionConfig,
    NYImpulseMeanReversionStrategy,
)
from eurusd_quant.strategies.session_breakout import SessionBreakoutConfig, SessionRangeBreakoutStrategy
from eurusd_quant.strategies.trend_exhaustion_reversal import (
    TrendExhaustionReversalConfig,
    TrendExhaustionReversalStrategy,
)
from eurusd_quant.strategies.volatility_expansion_after_compression import (
    VolatilityExpansionAfterCompressionConfig,
    VolatilityExpansionAfterCompressionStrategy,
)
from eurusd_quant.strategies.vwap_intraday_reversion import (
    VWAPIntradayReversionConfig,
    VWAPIntradayReversionStrategy,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run EURUSD strategy backtest")
    parser.add_argument("--input", required=True, help="Path to input parquet bars")
    parser.add_argument("--strategy", required=True, help="Strategy key from config/strategies.yaml")
    parser.add_argument("--output-dir", required=True, help="Output directory for results")
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    args = parse_args()

    execution_cfg = load_yaml(ROOT / "config" / "execution.yaml")
    strategy_cfg_all = load_yaml(ROOT / "config" / "strategies.yaml")
    if args.strategy not in strategy_cfg_all:
        raise ValueError(f"Unsupported strategy: {args.strategy}")

    bars = load_bars(args.input)

    if args.strategy == "session_breakout":
        strategy_cfg = SessionBreakoutConfig.from_dict(strategy_cfg_all["session_breakout"])
        strategy = SessionRangeBreakoutStrategy(strategy_cfg)
    elif args.strategy == "asian_range_compression_breakout":
        strategy_cfg = AsianRangeCompressionBreakoutConfig.from_dict(
            strategy_cfg_all["asian_range_compression_breakout"]
        )
        strategy = AsianRangeCompressionBreakoutStrategy(strategy_cfg)
    elif args.strategy == "compression_breakout":
        strategy_cfg = CompressionBreakoutConfig.from_dict(
            strategy_cfg_all["compression_breakout"]
        )
        strategy = CompressionBreakoutStrategy(strategy_cfg)
    elif args.strategy == "compression_breakout_continuation":
        strategy_cfg = CompressionBreakoutContinuationConfig.from_dict(
            strategy_cfg_all["compression_breakout_continuation"]
        )
        strategy = CompressionBreakoutContinuationStrategy(strategy_cfg)
    elif args.strategy == "false_breakout_reversal":
        strategy_cfg = FalseBreakoutReversalConfig.from_dict(
            strategy_cfg_all["false_breakout_reversal"]
        )
        strategy = FalseBreakoutReversalStrategy(strategy_cfg)
    elif args.strategy == "london_pullback_continuation":
        strategy_cfg = LondonPullbackContinuationConfig.from_dict(
            strategy_cfg_all["london_pullback_continuation"]
        )
        strategy = LondonPullbackContinuationStrategy(strategy_cfg)
    elif args.strategy == "london_open_impulse_fade":
        strategy_cfg = LondonOpenImpulseFadeConfig.from_dict(
            strategy_cfg_all["london_open_impulse_fade"]
        )
        strategy = LondonOpenImpulseFadeStrategy(strategy_cfg)
    elif args.strategy == "head_shoulders_reversal":
        strategy_cfg = HeadShouldersReversalConfig.from_dict(
            strategy_cfg_all["head_shoulders_reversal"]
        )
        strategy = HeadShouldersReversalStrategy(strategy_cfg)
    elif args.strategy == "impulse_session_open":
        strategy_cfg = ImpulseSessionOpenConfig.from_dict(
            strategy_cfg_all["impulse_session_open"]
        )
        strategy = ImpulseSessionOpenStrategy(strategy_cfg)
    elif args.strategy == "ny_impulse_mean_reversion":
        strategy_cfg = NYImpulseMeanReversionConfig.from_dict(
            strategy_cfg_all["ny_impulse_mean_reversion"]
        )
        strategy = NYImpulseMeanReversionStrategy(strategy_cfg)
    elif args.strategy == "vwap_intraday_reversion":
        strategy_cfg = VWAPIntradayReversionConfig.from_dict(
            strategy_cfg_all["vwap_intraday_reversion"]
        )
        strategy = VWAPIntradayReversionStrategy(strategy_cfg)
    elif args.strategy == "volatility_expansion_after_compression":
        strategy_cfg = VolatilityExpansionAfterCompressionConfig.from_dict(
            strategy_cfg_all["volatility_expansion_after_compression"]
        )
        strategy = VolatilityExpansionAfterCompressionStrategy(strategy_cfg)
    elif args.strategy == "trend_exhaustion_reversal":
        strategy_cfg = TrendExhaustionReversalConfig.from_dict(
            strategy_cfg_all["trend_exhaustion_reversal"]
        )
        strategy = TrendExhaustionReversalStrategy(strategy_cfg)
    else:
        raise ValueError(f"Strategy wired in config but not implemented in runner: {args.strategy}")

    simulator = ExecutionSimulator(ExecutionConfig.from_dict(execution_cfg))

    for _, bar in bars.iterrows():
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

    if not bars.empty:
        simulator.close_open_position_at_end(bars.iloc[-1])

    trades_df = simulator.get_trades_df()
    metrics = compute_metrics(trades_df)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades_path = output_dir / "trades.parquet"
    metrics_path = output_dir / "metrics.json"
    trades_df.to_parquet(trades_path, index=False)
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print("Backtest complete")
    print(f"Trades saved to: {trades_path}")
    print(f"Metrics saved to: {metrics_path}")
    for key, value in metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
