# London Pullback Continuation Strategy (Research Summary)

## Strategy hypothesis
The idea was to use pre-London directional context and enter continuation after a pullback:
- measure overnight/pre-London drift
- wait for a pullback after London open
- enter continuation when the pullback resolves
- trade only in 08:00-10:00 UTC

Motivation: earlier EURUSD intraday research showed time-of-day and overnight drift mattered, while raw breakout continuation and false-break reversal were not robust enough.

## Implementation summary
Implemented MVP strategy: `london_pullback_continuation`.

Core behavior:
- overnight drift: `mid_close(07:45) - mid_close(00:00)`
- bias requires drift threshold
- pullback reference: EMA20 on `mid_close`
- ATR minimum filter
- ATR-based stop
- ATR-target take profit
- one trade per day
- `allowed_side` configurable (MVP evaluated in default form)

## Datasets used
Primary dataset for this strategy research:
- EURUSD M15 bars
- combined 2018-2024 dataset
- source pipeline: Dukascopy ticks converted to bid/ask-aware M15 bars

## Experiments performed
1. Initial implementation and smoke backtest on 2018-2024 combined bars.

## Key findings
Smoke-test metrics:
- total_trades: 571
- win_rate: 0.4326
- net_pnl: -0.0331946428571549
- expectancy: -5.8134225669273025e-05
- profit_factor: 0.8789
- max_drawdown: 0.037733214285717964

## Interpretation
- First-pass behavior was not promising.
- Profit factor below 1 on a broad multi-year sample indicates weak edge.
- This idea is not worth further refinement at this stage.
- The negative result is still useful because it rules out another common London-open continuation pattern.

## Final conclusion
The `london_pullback_continuation` strategy was researched and tested on the 2018-2024 EURUSD dataset, but first-pass results were not strong enough to justify further refinement at this stage.

Classification: **researched but not promising**.

## Lessons learned
- Overnight drift alone is not enough to create a robust London continuation edge.
- London-open continuation ideas should not be assumed to work without evidence.
- Broad multi-year smoke tests are effective for rejecting weak hypotheses quickly.
- Early rejection reduces overfitting risk.

## Future revisit options
Revisit only under materially different conditions:
- different FX pairs
- meaningfully different pullback definition
- stronger regime/context filter
- fundamentally different entry logic

## Related outputs
- `outputs/london_pullback_continuation_smoke/`
