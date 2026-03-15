# Portfolio Candidate Analysis

## Phase 6 Follow-Up

This document is still the right place for the portfolio-level read across surviving sleeves, but it should now be read together with the focused NY impulse validation in [ny_impulse_mean_reversion_validation.md](ny_impulse_mean_reversion_validation.md).

Latest change:

- `ny_impulse_mean_reversion` no longer survives as an active candidate after the focused validation pass
- full-sample standalone metrics remained positive, but the sleeve still failed OOS density and concentration requirements
- a small portfolio context check with `false_breakout_reversal` was negative:
  - standalone `ny_impulse`: `net_pnl 0.03750`, `PF 1.4637`, `max_drawdown 0.01489`
  - `ny_impulse + false_breakout`: `net_pnl -0.01255`, `PF 0.9600`, `max_drawdown 0.03515`

Current interpretation:

- the portfolio layer remains useful for governance
- the candidate set is now cleaner, but also smaller
- the current evidence does not support paper-trading preparation

## Phase 5 Follow-Up

This Phase 4 analysis remains useful as the baseline portfolio reference, but it should now be read together with the Phase 5 candidate-strengthening reruns in [candidate_strengthening_results.md](candidate_strengthening_results.md).

Key follow-up changes:

- the GBPUSD trend sleeve was rechecked on session-aligned daily bars and no longer improved the portfolio
- the EURUSD continuation slot was rerun with a tighter `07:00-08:00 UTC` focus and still failed
- `ny_impulse_mean_reversion` improved after tightening the threshold to `22.0` pips, which lifted the updated EURUSD core from `-0.01972` net pnl to `+0.00104` with max drawdown reduced from `0.03195` to `0.01952`

Current interpretation:

- the portfolio layer is still useful
- the candidate set is less misleading than it was in Phase 4
- the research basket is still not strong enough for operational work

## Candidate Members

Core candidate portfolio members used in this phase:

- `london_pullback_continuation` on `EURUSD` (`15m`)
- `false_breakout_reversal` on `EURUSD` (`15m`)
- `ny_impulse_mean_reversion` on `EURUSD` (`15m`)

Exploratory add-on:

- `tsmom_ma_cross` on `GBPUSD` (`1d`)

## Artifact Inputs

Artifacts were generated into:

- `outputs/portfolio_inputs/london_pullback_continuation_eurusd/`
- `outputs/portfolio_inputs/false_breakout_reversal_eurusd/`
- `outputs/portfolio_inputs/ny_impulse_mean_reversion_eurusd/`
- `outputs/portfolio_inputs/tsmom_ma_cross_gbpusd/`

## Commands Run

### Candidate artifact generation

```bash
.venv/bin/python scripts/run_backtest.py --input /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet --strategy london_pullback_continuation --output-dir outputs/portfolio_inputs/london_pullback_continuation_eurusd
.venv/bin/python scripts/run_backtest.py --input /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet --strategy false_breakout_reversal --output-dir outputs/portfolio_inputs/false_breakout_reversal_eurusd
.venv/bin/python scripts/run_backtest.py --input /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet --strategy ny_impulse_mean_reversion --output-dir outputs/portfolio_inputs/ny_impulse_mean_reversion_eurusd
.venv/bin/python scripts/run_backtest.py --input /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/1d/gbpusd_bars_1d_2018_2024.parquet --strategy tsmom_ma_cross --output-dir outputs/portfolio_inputs/tsmom_ma_cross_gbpusd
```

### Correlation diagnostics

```bash
.venv/bin/python scripts/analyze_strategy_correlation.py \
  --config config/portfolio_candidates.yaml \
  --output-dir outputs/strategy_correlation
```

### Portfolio backtests

```bash
.venv/bin/python scripts/run_portfolio_backtest.py \
  --config config/portfolio_candidates.yaml \
  --output-dir outputs/portfolio_candidates
```

## Correlation Findings

### Core EURUSD set

- pairwise daily PnL correlation was low to slightly negative
- average pairwise correlation: `-0.0581`
- max pairwise correlation: `0.0552`

This indicates the three surviving EURUSD archetypes are not trivially identical in realized daily PnL space.

### Overlap

- `false_breakout_reversal` vs `london_pullback_continuation`: `447` overlapping active days, overlap ratio `0.7828`
- `false_breakout_reversal` vs `ny_impulse_mean_reversion`: `179` overlapping active days, overlap ratio `0.7103`
- `london_pullback_continuation` vs `ny_impulse_mean_reversion`: `88` overlapping active days, overlap ratio `0.3492`

Interpretation:
The PnL correlations are modest, but the core set is still heavily concentrated in EURUSD and frequently active at the same time. Correlation alone is not enough to claim strong diversification.

### Exploratory trend sleeve

- `tsmom_ma_cross` on GBPUSD had near-zero correlation with the EURUSD intraday streams:
  - vs `london_pullback_continuation`: `-0.0030`
  - vs `false_breakout_reversal`: `-0.0288`
  - vs `ny_impulse_mean_reversion`: `-0.0285`

That is genuine pair/timeframe diversification, but it comes from an exploratory trend member that is not yet strategy-promoted.

## Portfolio Metrics

### Core candidate set

| portfolio | net_pnl | profit_factor | max_drawdown | return_to_drawdown |
|---|---:|---:|---:|---:|
| `core_equal_weight` | `-0.02263` | `0.9352` | `0.03607` | `-0.6275` |
| `core_inverse_vol` | `-0.02178` | `0.9265` | `0.02964` | `-0.7350` |
| `core_inverse_vol_capped` | `-0.00979` | `0.9660` | `0.02193` | `-0.4465` |

Observation:
Exposure-aware sizing improved drawdown and reduced the loss, but the core EURUSD candidate set still remained negative.

### Exploratory trend comparison

| portfolio | net_pnl | profit_factor | max_drawdown | return_to_drawdown |
|---|---:|---:|---:|---:|
| `exploratory_without_trend` | `-0.01972` | `0.9334` | `0.03195` | `-0.6171` |
| `exploratory_with_trend` | `0.10919` | `1.3813` | `0.01844` | `5.9197` |

Observation:
Adding the GBPUSD trend sleeve dramatically changed the result, but the gain was not broadly shared by the other members.

## Contribution Analysis

`exploratory_with_trend` contribution by strategy:

- `tsmom_ma_cross_gbpusd`: `+0.12405`
- `false_breakout_eurusd`: `-0.00395`
- `london_pullback_eurusd`: `-0.01022`
- `ny_impulse_eurusd`: `-0.00069`

Interpretation:
The only positive exploratory portfolio is dominated by the trend sleeve. That means the apparent improvement is real diversification in one sense, but not yet a stable multi-member portfolio story.

## Drawdown Comparison

- inverse-vol plus caps improved the core portfolio drawdown from `0.03607` to `0.02193`
- the exploratory-with-trend portfolio had the best drawdown of the tested set at `0.01844`

This is directionally encouraging, but the drawdown improvement should not be mistaken for a robust portfolio result when one member contributes nearly all of the net PnL.

## Conclusions

- diversification inside the EURUSD core set is only partial: correlations are low, but overlap and concentration are still high
- exposure caps help the core set behave less badly, but they do not make it good
- the exploratory GBPUSD trend sleeve adds genuine diversification, but it currently dominates the portfolio outcome
- the current candidate set is not yet strong enough to claim a portfolio-ready research basket

## Bottom Line

Phase 4 was still useful:

- the repo now has a clean portfolio/risk layer
- redundancy and overlap are measurable
- exposure caps can be tested explicitly
- the trend sleeve can be compared rather than argued about abstractly

But the honest conclusion is that the current portfolio is still too weak and too dependent on one exploratory member to justify operational promotion.
