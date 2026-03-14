# Candidate Strengthening Results

## Objective

Phase 5 asked a narrow question:

- can the current candidate set be strengthened enough to justify further portfolio work
- or should weak survivors be rejected more decisively before any paper-trading preparation

This phase touched only three tracks:

1. `tsmom_ma_cross` on `GBPUSD`
2. `session_breakout` on `EURUSD`
3. `ny_impulse_mean_reversion` on `EURUSD`

## Data And Commands

Primary datasets:

- `EURUSD` 15m bars, `2018-2024`
- `GBPUSD` 15m bars, `2018-2024`
- session-aligned daily bars rebuilt with fixed `22:00 UTC` rollover for trend revalidation

Key commands:

```bash
.venv/bin/python scripts/prepare_higher_timeframe_bars.py \
  --input-file /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/gbpusd_bars_15m_2018_2024.parquet \
  --output-file outputs/candidate_strengthening/bars/gbpusd_bars_1d_session22_2018_2024.parquet \
  --timeframe 1d \
  --session-rollover-hour-utc 22

.venv/bin/python scripts/run_walk_forward_validation.py \
  --strategy tsmom_ma_cross \
  --bars outputs/candidate_strengthening/bars/gbpusd_bars_1d_session22_2018_2024.parquet \
  --input-configs outputs/candidate_strengthening/configs/tsmom_ma_cross_focus.csv \
  --train-years 3 \
  --test-months 6 \
  --output-dir outputs/candidate_strengthening/trend_walk_forward/tsmom_ma_cross_gbpusd_session22

.venv/bin/python scripts/run_window_experiments.py \
  --bars /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --strategy session_breakout \
  --output-root outputs/candidate_strengthening/session_breakout/window_experiments \
  --run-stress \
  --stress-spread-penalty-pips 0.2

.venv/bin/python scripts/run_buffer_experiments.py \
  --bars /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --strategy session_breakout \
  --output-root outputs/candidate_strengthening/session_breakout/buffer_experiments \
  --run-stress \
  --stress-spread-penalty-pips 0.2

.venv/bin/python scripts/run_walk_forward_validation.py \
  --strategy ny_impulse_mean_reversion \
  --bars /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --input-configs outputs/candidate_strengthening/configs/ny_impulse_focus.csv \
  --train-years 3 \
  --test-months 6 \
  --output-dir outputs/candidate_strengthening/ny_impulse/walk_forward
```

## Track A: `tsmom_ma_cross` On GBPUSD

### Prior baseline

From Phase 2 exploratory work on pre-session-alignment daily bars:

- OOS trades: `149`
- OOS profit factor: `1.2235`
- OOS net pnl: `0.147321`
- OOS max drawdown: `0.092066`

### Session-aligned revalidation

Main config: `fast=20`, `slow=50`, `atr_stop=1.5`, `trailing_stop=true`

- GBPUSD session-aligned WFO:
  - trades: `594`
  - profit factor: `0.8744`
  - net pnl: `-0.20409`
  - max drawdown: `0.23982`
- stressed / harsh PF: `0.8292` / `0.7901`

Neighborhood on GBPUSD session-aligned bars:

- `10/50, trailing=true`: PF `0.8621`
- `20/100, trailing=true`: PF `0.8077`
- `20/50, trailing=false`: PF `0.8744`

Cross-pair sanity check on session-aligned EURUSD bars:

- `20/50, trailing=true`: PF `0.8929`
- `10/50, trailing=true`: PF `0.9020`
- `20/100, trailing=true`: PF `0.7671`

### Verdict

`reject`

The prior GBPUSD strength does not survive the session-aware data correction. The same narrow parameter neighborhood also fails, and the EURUSD sanity check stays negative. This sleeve should not remain an exploratory portfolio crutch.

## Track B: `session_breakout` On EURUSD

### Failure mode

The earlier window research on partial 2023 data suggested the continuation idea might be concentrated in the `07:00-08:00 UTC` segment. The risk was that later London hours were diluting an otherwise usable edge.

### Focused refinement

Refinement tested:

- restrict entry to `07:00-08:00 UTC`
- test `breakout_buffer_atr` values `0.0`, `0.1`, `0.2`, `0.3`

### Full-sample diagnostics

Window comparison on `2018-2024`:

- `07:00-08:00`: PF `0.8903`, net pnl `-0.03481`
- `08:00-09:00`: PF `0.8913`, net pnl `-0.05641`
- `09:00-10:00`: PF `0.9177`, net pnl `-0.05271`

Best focused buffer run:

- `07:00-08:00`, `breakout_buffer_atr=0.2`
- PF `0.9162`
- net pnl `-0.02442`
- stressed PF `0.8302`

### Walk-forward comparison

Baseline config (`07:00-10:00`, buffer `0.0`):

- trades: `743`
- PF: `0.8171`
- net pnl: `-0.06064`
- max drawdown: `0.06228`

Best refined config (`07:00-08:00`, buffer `0.2`):

- trades: `343`
- PF: `0.8498`
- net pnl: `-0.02271`
- max drawdown: `0.02530`

### Verdict

`reject`

The focused continuation refinement reduced the loss, but it did not produce positive expectancy in-sample or OOS, and it failed cost stress. The continuation archetype should not remain in the active candidate pool in its current form.

## Track C: `ny_impulse_mean_reversion` On EURUSD

### Failure mode

The weaker active threshold (`17.5` pips) appears to admit too many low-quality NY impulse days. Earlier research already suggested the cleaner behavior was in the upper part of the impulse-size distribution.

### Focused refinement

Refinement tested:

- keep strategy identity unchanged
- tighten `impulse_threshold_pips` only
- compare `17.5`, `22.0`, `24.55`, `28.0`

### Full-sample threshold results

Baseline (`17.5` pips):

- trades: `252`
- PF: `1.0866`
- net pnl: `0.01428`
- max drawdown: `0.02812`

Refined (`22.0` pips):

- trades: `129`
- PF: `1.4637`
- net pnl: `0.03750`
- max drawdown: `0.01489`

Higher thresholds:

- `24.55` pips: PF `1.5577`, net pnl `0.03431`, trades `99`
- `28.0` pips: PF `1.4896`, net pnl `0.02210`, trades `67`

### Walk-forward comparison

Baseline (`17.5` pips):

- trades: `137`
- PF: `0.8889`
- net pnl: `-0.01117`
- max drawdown: `0.02812`

Refined (`22.0` pips):

- trades: `70`
- PF: `1.1459`
- net pnl: `0.00741`
- max drawdown: `0.01489`
- stressed / harsh PF: `1.1362` / `1.1265`

Stricter thresholds stayed positive but became too thin:

- `24.55` pips: trades `53`, PF `1.0631`
- `28.0` pips: trades `34`, PF `1.0656`

### Verdict

`improved, but not promoted`

`22.0` pips is the best current NY impulse threshold because it improves both OOS PF and drawdown versus the old default. It still fails the formal promotion framework on trade density and yearly concentration, so it should stay below `walk_forward_validated` status.

## Portfolio Recheck

Phase-specific portfolio metrics:

| portfolio | net_pnl | profit_factor | max_drawdown | return_to_drawdown |
|---|---:|---:|---:|---:|
| `candidate_strengthening_core_baseline` | `-0.01972` | `0.9334` | `0.03195` | `-0.6171` |
| `candidate_strengthening_core_updated` | `0.00104` | `1.0038` | `0.01952` | `0.0535` |
| `candidate_strengthening_exploratory_with_trend` | `-0.01451` | `0.9554` | `0.03122` | `-0.4650` |
| `candidate_strengthening_exploratory_without_trend` | `0.00104` | `1.0038` | `0.01952` | `0.0535` |

Contribution highlights:

- updated core:
  - `ny_impulse_eurusd_refined`: `+0.01066`
  - `false_breakout_eurusd`: `-0.00827`
  - `session_breakout_eurusd_refined`: `-0.00135`
- exploratory with trend:
  - `tsmom_ma_cross_gbpusd_session22`: `-0.01099`

Interpretation:

- the updated EURUSD core is less bad and nearly flat, mostly because the tighter NY impulse threshold offsets the weaker intraday sleeves
- the session-aligned GBPUSD trend sleeve no longer improves the portfolio; it now makes the exploratory basket worse
- dependence on one dominator decreased because the old trend sleeve stopped being a false positive, not because the full candidate set became robust

## Final Conclusion

This phase improved confidence more than it improved the candidate set.

- `tsmom_ma_cross_gbpusd` should be rejected under the session-aware daily-bar convention
- the continuation sleeve should be frozen in current form
- `ny_impulse_mean_reversion` is the only sleeve that improved materially, but it still falls short of formal promotion
- the updated portfolio is less fragile than the old baseline, but it is still too weak to justify paper-trading preparation

Current recommendation:

- continue research only on the event / reversal sleeves that still have real evidence
- do not start a paper-trading MVP from the current candidate set
