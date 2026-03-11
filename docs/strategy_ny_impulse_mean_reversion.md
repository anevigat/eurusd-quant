# NY Impulse Mean Reversion Strategy Research Summary

## Strategy hypothesis

The New York session often begins with a strong directional impulse caused by liquidity imbalance or macro news flow. In some cases, the initial move becomes overextended and price partially mean-reverts toward the impulse midpoint.

The strategy attempts to:

- detect unusually large NY session opening impulses
- wait for partial retracement
- enter in the opposite direction
- capture the mean-reversion move

## Dataset used

Primary dataset for this research:

- EURUSD 15-minute bars
- source: Dukascopy tick data
- prepared with repository pipeline: download -> clean ticks -> build 15m bars -> add sessions

Backtest range used for core validation:

- 2018-01-01 -> 2024-12-31

## Strategy implementation summary

Final tested strategy:

- `strategy`: `ny_impulse_mean_reversion`
- NY impulse window: `13:00-13:30 UTC`
- entry window: `13:30-15:00 UTC`
- impulse threshold selected from quantile analysis (`p90`)

Final configuration used for robustness workflow:

- impulse threshold: `p90` (`0.002455`, about `24.55` pips on EURUSD)
- entry retracement ratio: `0.50`
- exit model: `atr_target`
- `atr_target_multiple`: `1.0`

Entry/exit flow:

1. detect NY opening impulse
2. wait for 50% retracement against impulse direction
3. enter opposite direction on retracement trigger
4. place stop beyond impulse extreme
5. target via ATR multiple

## Experiments performed

### 1. Impulse threshold experiments

Tested thresholds:

- `p50` (`12.65` pips)
- `p75` (`17.55` pips)
- `p90` (`24.55` pips)

Result summary:

- `p90` produced the strongest risk-adjusted profile (PF `1.5577`, net PnL `0.03431`, max DD `0.01186`).

### 2. Entry retracement experiments

Tested entry ratios:

- `0.30`
- `0.40`
- `0.50`

Result summary:

- `0.50` was best among tested entry levels (PF `1.5577`, net PnL `0.03431`).

### 3. Exit model experiments

Tested:

- retracement exits (`0.25`, `0.50`, `0.75`, `1.00`)
- ATR exits (`0.5`, `1.0`, `1.5`)

Result summary:

- ATR exits were consistently competitive.
- `atr_1.0` was selected as the baseline operational configuration for downstream stress/walk-forward tests.

### 4. Execution stress tests

Scenarios:

- `baseline`
- `spread_x2`
- `slippage_1pip`
- `slippage_2pip`

Result summary:

- strategy remained net-positive across all tested scenarios
- performance decayed materially as slippage increased, especially at `2` pips

### 5. Monte Carlo simulation

Setup:

- `1000` random trade-order shuffles
- returns from `outputs/ny_impulse_exit_models_extended/atr_1_0/trades.parquet`

Key risk stats:

- median max drawdown: `0.00906`
- p95 max drawdown: `0.01478`
- worst max drawdown: `0.01942`

### 6. Walk-forward validation

Design:

- rolling windows:
  - train `2018-2020` -> test `2021`
  - train `2019-2021` -> test `2022`
  - train `2020-2022` -> test `2023`
  - train `2021-2023` -> test `2024`

Result summary:

- all four test years were net-positive in this setup
- performance varied by regime and by number of trades per year

## Key metrics

Representative baseline metrics (`p90`, entry `0.50`, exit `atr_1.0`):

- total trades: `99`
- win rate: `0.6465`
- profit factor: `1.7408`
- net PnL: `0.04247`
- expectancy: `0.0004290`
- max drawdown: `0.01124`

Stress-test highlights:

- `spread_x2`: PF `1.6164`, net PnL `0.03676`
- `slippage_1pip`: PF `1.3785`, net PnL `0.02408`
- `slippage_2pip`: PF `1.0601`, net PnL `0.00428`

Walk-forward highlights:

- 2021 test: PF `154.14`, net PnL `0.00459` (very low sample)
- 2022 test: PF `1.04`, net PnL `0.00125`
- 2023 test: PF `1.27`, net PnL `0.00228`
- 2024 test: PF `2.27`, net PnL `0.00249`

## Extended Diagnostics and Regime Analysis

### 1. Volatility Regime Analysis

Method:

- computed daily ATR from 15m bars (True Range based)
- defined ATR quantile regimes:
  - `low_vol`: `<= p30`
  - `mid_vol`: `p30 < ATR <= p70`
  - `high_vol`: `> p70`

Results:

- `low_vol`: 7 trades, PF `23.52` (small sample)
- `mid_vol`: 17 trades, PF `1.47`
- `high_vol`: 75 trades, PF `1.64`

Interpretation:

- strategy performance is strongest in elevated-volatility environments, consistent with the NY impulse mean-reversion hypothesis.

### 2. Trend Regime Analysis

Method:

- daily trend strength:
  - `abs(close_23_45 - open_00_00)`
- regimes:
  - `range_day`
  - `normal_day`
  - `trend_day`

Results:

- `range_day`: 17 trades, PF `1.28`
- `normal_day`: 38 trades, PF `2.38`
- `trend_day`: 44 trades, PF `1.59`

Interpretation:

- best performance appears in moderate-trend environments, suggesting NY impulses often overreact but still mean-revert partially.

### 3. Impulse Size Regime Analysis

Method:

- impulses bucketed by quantile size within the NY impulse window.

Result:

- all live strategy trades mapped to `extreme_impulse` due to the existing `p90` threshold filter:
  - `extreme_impulse`: 99 trades, PF `1.74`

Interpretation:

- strategy is specifically targeting extreme NY opening impulses by design.

### 4. Entry Efficiency Analysis

Method:

- measured how close each actual entry was to the best achievable entry between entry and exit.

Results:

- trades: `99`
- mean efficiency: `0.56`
- median efficiency: `0.45`
- p25: `0.23`
- p75: `1.00`

Interpretation:

- entries are often somewhat early versus the best retracement point (consistent with a fixed 50% trigger), while a meaningful share still captures near-optimal entries.

### 5. Recent Data Validation (2025-now)

Holdout validation snapshot on 2025-now data:

- trades: `46`
- profit factor: `0.65`
- net PnL: negative

Interpretation:

- recent performance degraded versus the 2018-2024 sample.
- sample size is still limited; regime diagnostics continue to indicate strongest behavior in high-volatility conditions.
- this supports continuing paper-trading observation before any live deployment decision.

### 6. Strategy Edge Map

Best-performing conditions identified:

- elevated volatility
- moderate daily trend
- extreme NY session impulse

These conditions are broadly aligned with liquidity-shock and macro-driven NY session opens.

### 7. Current Status

The NY impulse mean reversion strategy has completed the research phase and has been moved to paper trading for live validation.

The strategy is **not approved for live trading** at this stage.

## Interpretation

- evidence supports an NY-session impulse mean-reversion effect on EURUSD in this dataset
- profitability is sensitive to execution costs; edge compression is visible under worse slippage
- trade frequency is relatively low in the strongest configuration
- results vary across market regimes and years, so robustness is moderate rather than absolute

## Final conclusion

This strategy showed the strongest robustness among the intraday ideas tested in this project.

It passed:

- parameter sensitivity checks (threshold and entry segmentation)
- walk-forward validation
- execution stress tests
- Monte Carlo robustness analysis

However, the edge is modest and execution-sensitive. The strategy was therefore advanced to paper-trading validation, not live deployment.

## Paper trading implementation

The strategy is integrated into the paper-trading stack:

- `scripts/run_live_signal_engine.py`
- `scripts/run_paper_trading_simulator.py`
- `scripts/run_paper_trading_loop.py`

Operational outputs:

- signals: `paper_trading/signals/`
- state: `paper_trading/state/`
- logs: `paper_trading/logs/`

## Future research directions

- cross-pair robustness testing
- multi-timeframe impulse analysis
- extended paper-trading observation

## Related outputs

- `outputs/ny_impulse_threshold_experiments/`
- `outputs/ny_impulse_entry_experiments/`
- `outputs/ny_impulse_exit_models_extended/`
- `outputs/ny_impulse_execution_stress/`
- `outputs/ny_impulse_montecarlo/`
- `outputs/ny_impulse_walkforward/`
