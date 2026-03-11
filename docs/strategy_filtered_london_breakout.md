# Filtered London Breakout — Diagnostic Research Summary

## 1. Strategy hypothesis

Hypothesis:

- the raw London opening breakout is too noisy
- a filtered variant may improve structure when:
  - Asian range is relatively compressed
  - breakout is confirmed by a **bar close** outside the range
  - continuation is measured only after confirmed breakout

Goal: test whether filtered breakouts improve follow-through and reduce adverse excursion.

## 2. Dataset used

- Instrument: EURUSD
- Timeframe: 15m bars
- Dataset: `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- Days analyzed: `1822`

## 3. Diagnostic methodology

Implemented in:

- `scripts/analyze_filtered_london_breakout.py`

Windows (`UTC`, `[start, end)`):

- Asian session: `00:00-07:00`
- London window: `07:00-10:00`

Per-day range features:

- `asian_high`, `asian_low`, `asian_range`
- `ATR(14)` computed on 15m bars
- `asian_range_atr_ratio = asian_range / ATR`

Compression filter:

- compressed day if `asian_range_atr_ratio <= p25` over full sample

Breakout confirmation:

- upside: `mid_close > asian_high`
- downside: `mid_close < asian_low`
- if both occur, keep first confirmation only

Post-confirmation structure:

- `follow_through_R` and `adverse_move_R`
- both normalized by Asian range (`R`)

## 4. Summary results

Compression:

- `compressed_day_frequency`: `0.2503`
- `asian_range_atr_ratio p25`: `4.5670`

Confirmed breakout frequency:

- all days: `0.8194`
- compressed days: `0.9452`

All confirmed breakouts:

- `median_follow_through_R_all_days`: `0.3824`
- `median_adverse_move_R_all_days`: `0.3906`

Compressed + confirmed breakouts:

- `median_follow_through_R_compressed_days`: `0.5139`
- `p75_follow_through_R_compressed_days`: `0.9691`
- `p90_follow_through_R_compressed_days`: `1.4799`
- `median_adverse_move_R_compressed_days`: `0.5625`

Directional compressed breakdown:

- upside median `follow/adverse`: `0.4966 / 0.5165`
- downside median `follow/adverse`: `0.5160 / 0.5888`

## 5. Interpretation

Findings:

- compression filter increases confirmed breakout participation
- median follow-through improves versus unfiltered confirmed set
- but adverse excursion remains higher than follow-through on compressed days
- this pattern persists in both upside and downside breakdowns

Interpretation:

- filtering improves continuation magnitude somewhat, but not enough to dominate adverse movement
- structure remains too fragile for immediate strategy implementation

## 6. Conclusion

Classification:

- researched but not promising

Reason:

- despite higher breakout frequency on compressed days and better follow-through tails, median adverse move still dominates median follow-through

## 7. Final status

- diagnostic research completed
- no strategy implementation added
- filtered London breakout is not recommended for MVP in current form

## Outputs

- `outputs/filtered_london_breakout_diagnostic/summary.json`
- `outputs/filtered_london_breakout_diagnostic/daily_metrics.csv`
- `outputs/filtered_london_breakout_diagnostic/distribution.csv`
