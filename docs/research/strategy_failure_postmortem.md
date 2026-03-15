# Strategy Failure Post-Mortem

## Scope

This reset reviews the full strategy tree that has existed in the repository so far and summarizes the main ways those ideas failed.

Generated datasets for this phase:

- `outputs/research/strategy_inventory.csv`
- `outputs/research/strategy_performance_dataset.csv`
- `outputs/research/failure_statistics/`
- `outputs/research/cross_pair_comparison.csv`

Important limitation:

- the repo contains broad `EURUSD` evidence, limited completed `GBPUSD` strategy evidence, and no completed `USDJPY` strategy-level backtests in committed artifacts
- `USDJPY` appears in cross-pair configs and research plans, but not in finished strategy result sets
- missing metrics remain null by design rather than being backfilled from guesses

## 1. Strategy Inventory Summary

Current post-mortem inventory:

- unique strategies found: `37`
- strategy/pair rows in the raw inventory: `40`
- status mix:
  - `1` active
  - `2` exploratory
  - `18` rejected
  - `19` frozen

By archetype:

| archetype | strategy rows |
|---|---:|
| session breakout continuation | `8` |
| event-combination strategies | `7` |
| session reversal / sweep reversal | `7` |
| trend / momentum | `6` |
| VWAP / midpoint mean reversion | `5` |
| pattern-based reversal | `5` |
| experimental / one-off | `1` |

By pair:

- `EURUSD`: `37` rows
- `GBPUSD`: `3` rows
- `USDJPY`: `0` completed strategy rows

Interpretation:

- the repo is overwhelmingly a `EURUSD` research tree
- `GBPUSD` evidence exists mainly through the trend family and NY-impulse cross-pair robustness check
- `USDJPY` is still a stated target, not a completed strategy test set

## 2. Performance Overview

Only `18` inventory rows had enough recorded metrics to support a clean PF-based summary.

PF distribution across those rows:

- mean PF: `0.9379`
- median PF: `0.8767`
- PF `< 1.0`: `12 / 18`
- PF `>= 1.0`: `6 / 18`

Trade-count distribution across rows with available trade counts:

- median trade count: `508`
- mean trade count: `1585.6`

That average trade count is misleading on its own because the repo contains both:

- very thin strategies such as `tsmom_donchian` (`34` trades)
- severe over-trading failures such as `head_shoulders_reversal` (`13066` trades)

Drawdown distribution across rows with available values:

- median max drawdown: `0.1157`
- mean max drawdown: `0.1636`

Interpretation:

- most tested implementations did not clear even the first profitability bar
- when PF was above `1.0`, the next failures were usually density, concentration, or cross-pair weakness
- the tree contains both under-trading and over-trading failures, which is a sign that the problem was structural rather than a single execution setting

## 3. Failure Mode Analysis

Failure frequencies from `outputs/research/failure_statistics/failure_by_mode.csv`:

| failure_mode | count | percent of 40 rows |
|---|---:|---:|
| `no_edge_after_costs` | `13` | `32.5%` |
| `false_breakout_noise` | `8` | `20.0%` |
| `portfolio_redundant` | `4` | `10.0%` |
| `parameter_instability` | `2` | `5.0%` |
| `overfit_parameter` | `2` | `5.0%` |
| `yearly_concentration` | `1` | `2.5%` |
| `too_few_trades` | `1` | `2.5%` |

Interpretation:

- the dominant failure was simple: after realistic costs, there was no durable edge
- breakout continuation ideas repeatedly devolved into noisy false-break behavior
- the later trend and NY-impulse work introduced a different failure class: the results were interesting enough to matter, but too narrow or too pair-specific to survive promotion

## 4. Archetype Outcomes

Average PF and trade count by archetype, using only rows with available metrics:

| archetype | avg PF | avg trade count | read-through |
|---|---:|---:|---|
| session breakout continuation | `0.9379` | `339.3` | Timing mattered, but costs and false-break noise dominated. |
| event-combination strategies | `0.8289` | `1328.5` | Many rich setups were easy to describe but weak in implementation. |
| session reversal / sweep reversal | `0.8625` | `518.0` | This tree produced the only surviving sleeve, but even that remains weak overall. |
| trend / momentum | `1.1100` | `347.2` | The best average headline PF, but not promotable once density, drawdown, alignment, and cross-pair rechecks were applied. |
| VWAP / midpoint mean reversion | `0.9736` | `1580.0` | Closest to break-even, still not enough after costs. |
| pattern-based reversal | `0.8011` | `9400.0` | Diagnostics often looked attractive; tradable implementations became noisy and over-active. |

Key archetype lessons:

- Breakout continuation:
  - the repo repeatedly found small timing differences, but not a durable continuation edge
  - continuation variants were too easy to rescue with segmentation logic and too weak once judged OOS

- Mean reversion / reversal:
  - generic sweep-only and session-fade branches were not robust
  - `false_breakout_reversal` remains the only active sleeve, but even its frozen-parameter multi-year summary was mixed and slightly negative in aggregate

- Event-combination:
  - these ideas generated many plausible structural narratives
  - the implementation step usually converted them into cost-sensitive, high-noise systems
  - `ny_impulse_mean_reversion` was the closest exception, but still failed density and concentration gates

- Trend / momentum:
  - this family behaved differently from the intraday reversal tree and did show some real-looking OOS behavior
  - once session-aware daily bars were introduced, the strongest GBPUSD sleeve failed and the family lost its best supporting evidence

- Pattern-heavy systems:
  - pattern diagnostics often found asymmetry in raw structure
  - direct tradable implementations over-triggered and collapsed under noise and costs

## 5. Cross-Pair Observations

Cross-pair comparison in `outputs/research/cross_pair_comparison.csv` shows:

- `EURUSD` dominates the evidence base
- `GBPUSD` has only three completed strategy rows:
  - `tsmom_ma_cross`
  - `tsmom_return_sign`
  - `ny_impulse_mean_reversion` cross-pair robustness check
- `USDJPY` has no completed strategy rows in this repo state

Observed pair differences:

- Trend / momentum:
  - early `GBPUSD` looked supportive for the trend family
  - session-aware revalidation later overturned the strongest `GBPUSD` MA-crossover sleeve
  - `tsmom_return_sign` kept moderate `GBPUSD` PF, but still failed broader promotion gates

- Event-combination:
  - NY impulse behavior was strongest on `EURUSD`
  - the `GBPUSD` cross-pair robustness batch stayed below PF `1.0`
  - current evidence points to a strongly pair-conditioned effect, not a broad multi-pair edge

- USDJPY:
  - there is no finished strategy-level result set to compare
  - future cross-pair claims should be treated as incomplete until `USDJPY` is actually tested end-to-end

## 6. Key Lessons

1. Most hypotheses failed at the simplest level: after costs, there was no persistent edge.
2. Breakout continuation ideas were especially vulnerable to false-break noise and hour-block selection bias.
3. Several strategies showed raw structural behavior in diagnostics, but implementation quality collapsed once actual entries, exits, and costs were applied.
4. Positive OOS PF alone was not enough. The trend family and NY-impulse work show that trade density, yearly concentration, and neighborhood stability are decisive filters.
5. Cross-pair robustness was introduced too late. By the time `GBPUSD` rechecks were done, the repo had already accumulated too much `EURUSD`-specific research weight.
6. The repo repeatedly produced either very sparse strategies or very noisy high-frequency failures. That points to weak underlying signal design, not just bad parameter selection.
7. The current tree is mostly a rejection archive. That is useful, but it means the next cycle should start from narrower, better-specified hypotheses rather than from more branch proliferation.

## 7. Implications For The Next Research Cycle

Future research should default to these constraints:

- require multi-pair feasibility earlier, not after a sleeve already looks attractive on `EURUSD`
- avoid hypotheses that depend on narrow time blocks unless the raw effect is first demonstrated outside a strategy wrapper
- treat parameter-neighborhood checks as mandatory, not as a final polish step
- prioritize minimum trade density and year-balance before deeper refinement
- prefer one clean regime filter over stacked rescue logic
- reject branches quickly when the only apparent edge comes from a single pair, a single threshold, or one dominant year

Recommended reset posture:

- keep the post-mortem datasets as the baseline memory of what failed
- start the next cycle from a short list of structural hypotheses, not from archived strategy names
- do not resume paper-trading work until there are multiple independently credible sleeves with real cross-pair support
