# NY Impulse Mean Reversion Validation

## Verdict

`reject`

The sleeve still shows a niche full-sample effect around large NY impulses, but the stronger interpretation does not survive the full validation stack:

- walk-forward OOS results stay too thin
- yearly concentration remains too high
- the threshold neighborhood is not broad enough in promotable territory
- minimal structural refinements do not change the conclusion
- small portfolio context does not rescue the sleeve

Under the project rule for this phase, ambiguous outcomes default to rejection.

## Hypothesis Recap

The working hypothesis was that unusually large `13:00-13:30 UTC` NY-session impulses create short-lived liquidity dislocations that often mean-revert during the next few 15m bars.

This phase asked whether that behavior is:

- broad enough in raw data
- stable enough across nearby thresholds
- dense enough in OOS trading
- useful enough in small portfolio context

## Data And Commands

Primary dataset:

- `EURUSD` `15m` bars, `2018-2024`

Key commands run:

```bash
.venv/bin/python scripts/run_backtest.py \
  --input /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --strategy ny_impulse_mean_reversion \
  --output-dir outputs/ny_impulse_validation/baseline_backtest

.venv/bin/python scripts/analyze_ny_impulse_behavior.py \
  --bars /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --output-dir outputs/diagnostics/ny_impulse_behavior/all_impulses

.venv/bin/python scripts/analyze_ny_impulse_behavior.py \
  --bars /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --threshold-pips 22 \
  --output-dir outputs/diagnostics/ny_impulse_behavior/threshold_22

.venv/bin/python scripts/analyze_trade_density.py \
  --trades outputs/ny_impulse_validation/baseline_backtest/trades.parquet \
  --output-dir outputs/diagnostics/ny_impulse_trade_density

.venv/bin/python scripts/run_cost_stress_validation.py \
  --strategy ny_impulse_mean_reversion \
  --bars /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --config-json '{"timeframe":"15m","impulse_start_utc":"13:00","impulse_end_utc":"13:30","entry_start_utc":"13:30","entry_end_utc":"15:00","impulse_threshold_pips":22.0,"entry_mode":"impulse_midpoint_cross","retracement_target_ratio":0.5,"stop_buffer_pips":2.0,"max_holding_bars":6,"atr_period":14,"exit_model":"retracement","atr_target_multiple":1.0,"retracement_entry_ratio":0.5,"atr_trail_multiple":0.8,"initial_stop_atr":1.0,"breakeven_trigger_atr":0.5,"trailing_start_atr":1.0,"one_trade_per_day":true,"allowed_side":"both"}' \
  --spread-multipliers 1.0,1.5,2.0 \
  --output-dir outputs/ny_impulse_validation/cost_stress_cli

.venv/bin/python scripts/run_walk_forward_validation.py \
  --strategy ny_impulse_mean_reversion \
  --bars /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --input-configs outputs/ny_impulse_validation/configs/threshold_neighborhood.csv \
  --train-years 3 \
  --test-months 6 \
  --output-dir outputs/ny_impulse_validation/walk_forward_thresholds
```

Portfolio context:

```bash
.venv/bin/python scripts/run_backtest.py \
  --input /Users/anevigat/FX/eurusd-quant/eurusd_quant/data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --strategy false_breakout_reversal \
  --output-dir outputs/ny_impulse_validation/portfolio_inputs/false_breakout_eurusd

.venv/bin/python scripts/run_portfolio_backtest.py \
  --config outputs/ny_impulse_validation/portfolio_context.yaml \
  --output-dir outputs/ny_impulse_validation/portfolio_context
```

## Data / Execution Checks

### Session alignment

- the strategy uses explicit UTC windows on `15m` bars
- it does not consume the `22:00 UTC` higher-timeframe rollover logic directly
- no session-definition bug was found in this phase

### Trade timestamp correctness

- impulse measurement uses only bars inside the impulse window
- midpoint-cross entries are detected on the signal bar and filled on the next bar open
- no lookahead issue was found in the current implementation path

### Cost sensitivity

Full-sample baseline at `22.0` pips remains positive even under spread-only stress:

| scenario | trades | PF | net pnl | max drawdown |
|---|---:|---:|---:|---:|
| baseline | `129` | `1.4637` | `0.03750` | `0.01489` |
| `+50%` spread | `129` | `1.4533` | `0.03689` | `0.01508` |
| `+100%` spread | `129` | `1.4430` | `0.03628` | `0.01527` |

Interpretation:

- the effect is not purely a spread artifact in full-sample form
- that is still not enough for promotion once OOS density and concentration are considered

## Raw Behavior Diagnostics

Artifacts:

- `outputs/diagnostics/ny_impulse_behavior/all_impulses/`
- `outputs/diagnostics/ny_impulse_behavior/threshold_22/`

### All impulses

- total NY impulse days: `1817`
- median impulse size: `12.65` pips
- mean signed reversion return:
  - `+1` bar: `+0.013` pips
  - `+2` bars: `-0.080` pips
  - `+4` bars: `-0.335` pips
  - `+8` bars: `+0.140` pips

Interpretation:

- unconditional NY impulses do not show a broad, clean short-horizon reversion effect
- the raw effect is weak and horizon-dependent before thresholding

### Thresholded impulses at `22.0` pips

- qualifying impulse days: `236`
- median impulse size: `28.40` pips
- mean signed reversion return:
  - `+1` bar: `+0.367` pips
  - `+2` bars: `+1.107` pips
  - `+4` bars: `+0.457` pips
  - `+8` bars: `+2.558` pips

Important asymmetry:

- down impulses are materially stronger than up impulses
- at `+2` bars, down-impulse signed reversion is `+3.150` pips while up-impulse signed reversion is `-1.079` pips

Interpretation:

- a thresholded subset does contain a real-looking raw effect
- but that effect is regime-thin and asymmetric, which raises implementation risk and reduces confidence in broad deployability

## Parameter Stability

Full-sample threshold screen:

| threshold | trades | PF | net pnl | max drawdown |
|---|---:|---:|---:|---:|
| `18` | `235` | `1.0906` | `0.01422` | `0.02812` |
| `20` | `179` | `1.1506` | `0.01864` | `0.02566` |
| `22` | `129` | `1.4637` | `0.03750` | `0.01489` |
| `24` | `107` | `1.4331` | `0.03005` | `0.01349` |
| `26` | `86` | `1.5644` | `0.03056` | `0.01171` |

Walk-forward OOS threshold screen:

| threshold | OOS trades | OOS PF | OOS net pnl | max drawdown | dominant year share |
|---|---:|---:|---:|---:|---:|
| `18` | `130` | `0.9115` | `-0.00851` | `0.02812` | `0.7496` |
| `20` | `98` | `0.8712` | `-0.01027` | `0.02566` | `0.5391` |
| `22` | `70` | `1.1459` | `0.00741` | `0.01489` | `0.5394` |
| `24` | `58` | `1.0172` | `0.00079` | `0.01349` | `0.7659` |
| `26` | `47` | `1.1291` | `0.00464` | `0.01171` | `0.5385` |

Interpretation:

- the full-sample shape is smooth enough to suggest the threshold is not a single-point accident
- the OOS shape is still not good enough for promotion
- `22` and `26` are the only clearly positive OOS points, but both are too thin on trade count
- `24` loses too much edge and `18/20` fail outright

This is the key reason the sleeve does not survive as an active candidate: the effect looks niche rather than broad enough to meet the repo’s promotion standard.

## Trade Density

Artifacts:

- `outputs/diagnostics/ny_impulse_trade_density/`

Baseline full-sample density at `22.0` pips:

- total trades: `129`
- zero-trade months: `27`
- longest zero-trade gap: `6` months

Signal-window contribution:

- `13:30`: `45` trades, `+0.00919` net pnl
- `13:45`: `32` trades, `-0.00012` net pnl
- `14:00`: `22` trades, `+0.00476` net pnl
- `14:15`: `8` trades, `+0.01030` net pnl
- `14:30`: `13` trades, `+0.00490` net pnl
- `14:45`: `9` trades, `+0.00848` net pnl

Important nuance:

- full-sample yearly concentration is not extreme because profitable years are spread out
- promotion still fails on OOS yearly trade density and OOS concentration, not on full-sample density alone

In OOS walk-forward terms, even the best threshold is too sparse:

- `22.0` pips: `70` total OOS trades
- minimum promotion gate: `200` total OOS trades and `50` trades per covered year

That shortfall is too large to treat as a minor maturity problem.

## Minimal Structural Refinements

This phase screened only tiny, hypothesis-driven variants and rejected them before full walk-forward:

| variant | trades | PF | net pnl | max drawdown |
|---|---:|---:|---:|---:|
| baseline both sides | `129` | `1.4637` | `0.03750` | `0.01489` |
| `long_only` | `66` | `1.4689` | `0.01899` | `0.00788` |
| `short_only` | `63` | `1.4586` | `0.01851` | `0.00984` |
| `long_only`, `max_holding_bars=4` | `66` | `1.4653` | `0.01649` | `0.00818` |
| `long_only`, entry end `14:30` | `60` | `1.2533` | `0.01026` | `0.00788` |

Interpretation:

- the raw diagnostic asymmetry suggested testing a one-sided variant
- executed-trade results did not materially improve
- the narrower entry-window variant degraded
- none of these screens justified another walk-forward branch

## Walk-Forward Validation

Best current configuration remains the Phase 5 baseline:

- threshold: `22.0` pips
- entry mode: `impulse_midpoint_cross`
- exit model: `retracement`
- max holding bars: `6`

Walk-forward OOS result:

- trades: `70`
- PF: `1.1459`
- net pnl: `0.00741`
- max drawdown: `0.01489`
- stressed PF: `1.1362`
- harsh PF: `1.1265`
- dominant positive-year share: `0.5394`

Interpretation:

- the sleeve is not cost-fragile in the generic Phase 1 stress framework
- but it still fails hard on trade density
- yearly concentration is still above the promotion ceiling
- the result is better described as a sparse niche than a promotable candidate

## Portfolio Context

Small portfolio context check against the remaining reversal sleeve:

| portfolio | net pnl | PF | max drawdown | return / drawdown |
|---|---:|---:|---:|---:|
| `ny_impulse_standalone` | `0.03750` | `1.4637` | `0.01489` | `2.5191` |
| `ny_impulse_plus_false_breakout` | `-0.01255` | `0.9600` | `0.03515` | `-0.3570` |

Interpretation:

- the sleeve does not rescue the current intraday basket
- pairing it with `false_breakout_reversal` worsens the combined result despite slightly negative daily correlation
- the modest diversification story is not enough to override the sleeve’s sparse OOS profile

## Final Decision

`reject`

Why:

1. the strategy does appear to capture a real-looking thresholded subset, so this is not a trivial spread artifact
2. that subset is too thin and too concentrated once evaluated OOS
3. minimal structural refinements do not change the conclusion
4. small portfolio context does not make the sleeve operationally credible

This sleeve should remain as historical research evidence, not as an active candidate for paper-trading preparation.
