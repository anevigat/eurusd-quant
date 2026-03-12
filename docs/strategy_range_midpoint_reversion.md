# Range Midpoint Reversion — Diagnostic Summary

## Strategy hypothesis

Price may frequently revert toward important range midpoints (Asian midpoint or previous-day midpoint) during London/NY sessions.

## Dataset used

- EURUSD M15 bars
- `data/bars/15m/eurusd_bars_15m_2018_2024.parquet`
- sample: `1817` valid days

## Diagnostic methodology

Script:

- `scripts/analyze_range_midpoint_reversion.py`

Windows:

- Asian range: `00:00-07:00 UTC`
- London test window: `07:00-10:00 UTC`
- NY test window: `13:00-16:00 UTC`

Per day:

1. Compute Asian midpoint from Asian high/low
2. Compute previous-day midpoint from prior day high/low
3. Measure midpoint touch probabilities in London and NY

## Summary results

- `days_analyzed`: `1817`
- `asian_midpoint_hit_london_frequency`: `0.7430`
- `asian_midpoint_hit_ny_frequency`: `0.4298`
- `prev_midpoint_hit_london_frequency`: `0.3974`
- `prev_midpoint_hit_ny_frequency`: `0.3566`

## Interpretation

- Midpoint touches are common, especially Asian midpoint during London.
- This confirms structural tendency but does not provide directional or payoff asymmetry by itself.
- As a standalone concept, midpoint touch frequency is not sufficient for a robust strategy.

## Conclusion

Verdict: `researched_but_not_promising`

Classification: diagnostic complete, rejected for MVP implementation in current unfiltered form.

## Outputs

- `outputs/range_midpoint_reversion_diagnostic/summary.json`
- `outputs/range_midpoint_reversion_diagnostic/daily_metrics.csv`
- `outputs/range_midpoint_reversion_diagnostic/distribution.csv`
