# Portfolio Construction Plan

## Hypothesis

Standalone strategy results do not tell the full story. Some modest strategies may still be useful if they diversify across time, across pairs, or across regimes, and if a simple portfolio layer can improve drawdown behavior without hiding concentrated risk.

## Sizing Philosophy

This phase deliberately uses only simple allocation rules:

- `equal_weight`
- `inverse_vol`
- `capped_inverse_vol`

That keeps the portfolio layer explainable and avoids optimizer overfitting. If the candidate set cannot look coherent under these simple rules, it is too early to introduce anything more complex.

## Exposure-Control Philosophy

The default posture is conservative:

- cap weight per strategy
- cap weight per pair
- cap same-USD directional exposure
- cap simultaneous active strategies on the same pair
- allow optional blocking of explicitly overlapping strategy pairs

These controls are rule-based, not predictive. They exist to stop cosmetic diversification where several members are really just the same position in different wrappers.

## Data Model Choice

The portfolio layer works from existing strategy trade artifacts rather than adding a new artifact format.

Each portfolio member is normalized into:

- strategy name
- pair
- timeframe
- standardized trade table
- realized daily trade PnL stream
- active-position-by-day footprint

This is enough for allocation, overlap diagnostics, and conservative exposure capping.

## Why Simple Allocation Is Preferred Now

- current candidate count is small
- cross-pair coverage is still thin
- several archetypes are only near-approved, not fully promoted
- complex optimizers would mostly fit noise in a sparse candidate set

Simple weighting is a better research filter at this stage.

## Limitations

- portfolio PnL is based on realized daily trade PnL, not full mark-to-market portfolio equity
- exposure controls are applied from active trade windows, not broker-grade live position state
- pair diversification is still limited by the current artifact set
- the exploratory trend sleeve is not yet a promoted strategy and must be treated as such

## Success Standard For This Phase

The portfolio layer is useful if it can answer:

- which candidate streams are highly redundant
- whether exposure caps materially improve drawdown behavior
- whether any apparent portfolio improvement is genuine or dominated by one member

It does not need to produce a paper-trade-ready portfolio yet.
