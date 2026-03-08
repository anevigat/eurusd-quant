# Asian Session Breakout Research Notes

## Strategy hypothesis

Original hypothesis:

- Compute Asian session range from `00:00-06:00 UTC`
- Trade breakouts during early London session
- Go long when price breaks above Asian high
- Go short when price breaks below Asian low
- Use ATR-based stop distance
- Use fixed risk multiple for take-profit

The expectation was that low-volatility Asian session behavior would transition into directional expansion during London open.

## Dataset used

- Source: Dukascopy tick data
- Instrument: EURUSD
- Timeframe: M15 bars
- Period analyzed: `2023-01-01` to `2023-06-22`
- Bars: `10,728`
- Cleaned ticks: `13,475,002` (~13.4M)
- Known limitations:
  - missing/corrupt `.bi5` files
  - continuity gaps in part of the sample
  - partial-year data only (not full 2023)

## Experiments performed

The following experiments were implemented and run in this repository:

1. Baseline backtest
2. Stress test (higher slippage and spread penalty)
3. Entry window segmentation
4. Breakout buffer filter
5. MFE/MAE excursion analysis
6. Asian range compression analysis

Selected metrics from the analyzed sample:

- Baseline: `104` trades, win rate `42.31%`, net PnL `+0.00351`, profit factor `1.085`
- Stress: net PnL `-0.00081`, profit factor `0.982` (edge does not hold)
- Entry windows (fixed UTC): `07:00-08:00` strongest, `08:00-09:00` weakest
- MFE/MAE median ratio: `~1.02`
- Compression correlation (`asian_range_pips` vs `london_move_pips`): `~0.41`

## Key findings

- Profitability is marginal and disappears under stress testing.
- Entry timing affects results, but does not produce robust structural edge by itself.
- Breakout buffer filtering does not materially improve robustness.
- MFE/MAE ratio is approximately `1`, indicating near-symmetric adverse/favorable movement.
- A narrow-Asian-range compression effect was not observed.
- In this sample, larger Asian ranges tended to precede larger London moves.

## Conclusion

The Asian session breakout strategy, as defined in this project, does not show strong structural support on the analyzed EURUSD sample.

Further parameter tuning is not recommended without additional regime filters.

## Future work

If this concept is revisited, prioritize:

- applying the strategy to other FX pairs
- adding volatility regime filters
- adding macro event filters
- testing reversal / false-breakout variants
