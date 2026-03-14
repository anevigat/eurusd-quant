# NY Impulse Mean Reversion Hypothesis

## Market Intuition

`ny_impulse_mean_reversion` is meant to test a narrow intraday FX hypothesis:

- large directional impulses during the early New York session can reflect temporary liquidity dislocations
- those dislocations may come from macro-news digestion, order-flow imbalance, or stop cascades
- once the first impulse is exhausted, liquidity providers or discretionary fades may pull price back toward the impulse midpoint

The strategy is not trying to predict the New York trend day. It is trying to isolate a short-horizon overreaction regime and fade it only after an extreme move is already visible.

## Key Assumptions

The current implementation depends on all of these being true:

1. impulse magnitude contains signal
   Normal NY-session movement should be filtered out; only unusually large moves should qualify.
2. the early NY window is the right regime
   The effect should be concentrated in the `13:00-13:30 UTC` impulse window and the immediate follow-up window.
3. reversion happens quickly
   The move should fade within a small number of 15m bars, not over an open-ended intraday horizon.
4. the edge is not purely a spread artifact
   The strategy should still make sense after spread stress and realistic next-bar execution.
5. the edge is not a single-threshold accident
   A narrow neighborhood around the chosen threshold should behave similarly enough to reduce single-point overfit risk.

## Current Rules

Current active baseline before this validation pass:

- timeframe: `15m`
- impulse window: `13:00-13:30 UTC`
- entry window: `13:30-15:00 UTC`
- threshold: `22.0` pips absolute impulse range
- entry mode: `impulse_midpoint_cross`
- retracement entry ratio: `0.5`
- exit model: `retracement`
- retracement target ratio: `0.5`
- stop buffer: `2.0` pips
- max holding bars: `6`
- one trade per day: `true`
- allowed side: `both`

Entry logic:

- bullish impulse: short only after price crosses back below the configured retracement level
- bearish impulse: long only after price crosses back above the configured retracement level
- fills use the existing simulator convention: submit on the signal bar, fill on the next bar open

Exit logic:

- default stop is beyond the impulse extreme plus buffer
- target is the configured retracement fraction of the impulse range
- hard time stop is `max_holding_bars`
- intraday flattening still respects the global execution configuration

Position sizing:

- unchanged from the repo’s current simulator assumptions
- one unit per signal inside the backtest engine, with portfolio weighting handled separately by the Phase 4 tooling

## Session And Execution Assumptions

This strategy does not depend on the higher-timeframe `22:00 UTC` FX rollover that was added for 4H/1D trend aggregation.

- signals are generated directly from `15m` bars
- session logic uses explicit UTC windows via `in_time_window`
- the important session assumption here is the NY impulse window itself, not the daily rollover anchor

Trade timestamp correctness still matters:

- impulse measurement uses only bars inside the impulse window
- entry requires a cross on the current bar and fills on the next bar open
- exits are evaluated on subsequent bars with the standard simulator rules

## Failure Modes Observed Before This Phase

Phase 5 already showed why the sleeve was not promotable:

- weaker thresholds admitted too many low-quality impulse days
- the tightened `22.0`-pip threshold improved OOS PF and drawdown, but trade density remained too low for formal promotion
- OOS contribution was still too concentrated in a small subset of years
- portfolio help was modest and did not create a durable multi-sleeve story

This phase is meant to decide whether those problems are fixable with small, structural, hypothesis-driven adjustments or whether the sleeve should be rejected.
