# Liquidity Sweep Reversal — Diagnostic Summary

## Strategy hypothesis

When price sweeps a prior obvious liquidity level and quickly returns inside, reversal may follow.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1821` analyzed days

## Diagnostic methodology

Script:

- `scripts/analyze_liquidity_sweep_reversal.py`

Setup:

- reference levels: prior-day high/low
- analysis window: `07:00-17:00 UTC`
- sweep confirmation: level breach then close back inside within `4` bars
- reversal horizon: `8` bars after return-inside
- normalization: follow-through/adverse move in units of prior-day range (`R`)

## Summary results

- `days_analyzed`: `1821`
- `sweep_frequency`: `0.6798`
- `bullish_sweep_frequency`: `0.5048`
- `bearish_sweep_frequency`: `0.4952`
- `reversal_probability`: `0.4959`
- `median_follow_through_R`: `0.1979`
- `median_adverse_move_R`: `0.1908`
- `p75_follow_through_R`: `0.4246`

## Interpretation

- Sweeps are frequent, but reversal probability is near random.
- Median follow-through and adverse excursion are very close.
- No robust directional asymmetry appears in this formulation.

## Conclusion

Verdict: `researched_but_not_promising`

Final status: diagnostic complete, rejected in current form.

## Outputs

- `outputs/liquidity_sweep_reversal_diagnostic/summary.json`
- `outputs/liquidity_sweep_reversal_diagnostic/daily_metrics.csv`
- `outputs/liquidity_sweep_reversal_diagnostic/distribution.csv`
