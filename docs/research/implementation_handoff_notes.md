# Implementation Handoff Notes

Next coding branch should implement in this order:

1. `EXP_H1A_01`
2. `EXP_H1A_02`
3. `EXP_H1B_01`
4. `EXP_H2_01`

Allowed experimental knobs:

- breach-close vs one-bar confirmation for `H1A`
- one minimal timing sensitivity check for `H2`
- no extra filters beyond the locked session, range, breach, and horizon conditions

Not allowed in the first implementation cycle:

- widening pair scope for `H2`
- reviving `H3`
- adding extra regime filters
- broad entry/exit grids
- alternative holding horizons outside the bounded plan

The next branch should stop quickly if:

- smoke backtests are negative
- cost stress flips the sign immediately
- walk-forward is unstable
- pooled `EURUSD|GBPUSD` results hide contradiction
