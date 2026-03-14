# Intraday Strategy Consolidation

## Overview

The repository accumulated a large number of intraday diagnostics, MVPs, and minor variants. That was useful for rejection, but it left the research tree harder to navigate than it needed to be. Phase 3 consolidates the tree around a small number of archetypes and freezes the weak families so future work has a narrower mandate.

This is a governance pass, not a strategy-development pass:

- no new strategies
- no strategy logic changes
- no threshold changes
- no claim that rejected branches became good later

## Archetypes Identified

1. `session breakout continuation`
2. `session reversal / sweep reversal`
3. `VWAP / midpoint mean reversion`
4. `pattern-based reversal`
5. `event-combination strategies`
6. `trend / momentum`
7. `experimental / one-off`

## Active Archetypes

The repo should continue only these archetypes for now:

1. `session breakout continuation`
   Survivor focus: `london_pullback_continuation`, with `session_breakout` and related diagnostics kept as reference only.
2. `session reversal / sweep reversal`
   Survivor focus: `false_breakout_reversal`.
3. `event-combination strategies`
   Survivor focus: `ny_impulse_mean_reversion`.
4. `trend / momentum`
   Survivor focus: the Phase 2 `tsmom_*` family, but only after session-aligned-bar rechecks and without immediate re-optimization.

## Frozen Families

### Session-open fades and impulse-open variants

Frozen branches:

- `london_open_impulse_fade`
- `impulse_session_open`
- `vwap_session_open`

Reason:
These variants repeatedly produced weak expectancy or weak robustness and mainly encouraged parameter churn around opening-window behavior.

### VWAP / midpoint mean reversion

Frozen branches:

- `vwap_intraday_reversion`
- `session_vwap_reversion`
- `vwap_band_reversion_filtered`
- `range_midpoint_reversion`
- `vwap_session_open`

Reason:
The family was explored broadly enough to show that small formulation changes were not producing durable promotion-quality results.

### Pattern-based reversals and exhaustion patterns

Frozen branches:

- `head_shoulders_reversal`
- `double_top_bottom_reversal`
- `cup_handle_breakout`
- `trend_exhaustion_reversal`
- `double_impulse_exhaustion`

Reason:
These branches are especially exposed to narrative overfitting and sample scarcity. They produced readable stories more easily than durable edges.

### Compression / volatility breakout variants

Frozen branches:

- `asian_range_compression_breakout`
- `volatility_expansion_after_compression`
- `compression_breakout`
- `compression_breakout_continuation`
- `atr_spike_new_high_low`

Reason:
The repo already tested this theme from several angles. Repeated reformulations did not produce a branch that clearly beat simpler continuation or event-driven alternatives.

### Miscellaneous one-off diagnostics

Frozen branches:

- `asia_drift_london_reversal`
- `liquidity_sweep_reversal`
- `session_liquidity_sweep_reversal`
- `ny_liquidity_sweep_reversal`
- `daily_extreme_move_reversal`
- `multi_day_momentum_continuation`

Reason:
These notes remain useful as historical evidence, but they are not where the repo should spend its next iteration cycles.

## Lessons From Rejected Strategies

- Minor parameter or filter changes rarely rescued a weak base hypothesis.
- Session-open logic generated many tempting variants, but most were brittle once costs and wider samples mattered.
- Pattern-heavy branches were especially vulnerable to small sample sizes and selective interpretation.
- VWAP and midpoint reversion ideas were not underexplored; they were explored enough to justify freezing them.
- When a family was strong enough to survive, it usually did so with a simple statement of the edge rather than with layered filters.

## Overfitting Risk In Pattern-Heavy Systems

Pattern-heavy systems create two kinds of overfitting pressure:

1. semantic overfitting
   The pattern label itself makes weak evidence look richer than it is.
2. branch overfitting
   Once a pattern is named, it becomes easy to justify more variants instead of rejecting the base idea.

That is why these families are now frozen as historical reference rather than left implicitly active.

## Next Research Directions

1. Re-run the surviving continuation, reversal, and event-combination archetypes through the formal promotion framework rather than adding more sibling variants.
2. Treat the Phase 2 trend family as active but still exploratory until the most promising configs are rechecked on session-aligned bars.
3. Move next to portfolio/risk orchestration once the active archetypes are as clean as they are going to get.

## Consolidated Inventory

### Implemented Strategies

| strategy | archetype | timeframe | hypothesis | current status | last evaluation dataset | notes |
|---|---|---|---|---|---|---|
| `session_breakout` | session breakout continuation | `15m` | Asian/session range breaks may continue through London. | `diagnostic` | EURUSD 15m 2018-2024 diagnostics | Active archetype baseline, but not a signal to expand variants. |
| `london_pullback_continuation` | session breakout continuation | `15m` | Pre-London directional drift may resume after a shallow pullback. | `candidate` | EURUSD 15m 2018-2024 MVP analysis | Best current continuation survivor. |
| `false_breakout_reversal` | session reversal / sweep reversal | `15m` | Failed Asian/London breakouts may reverse back through the range. | `multi_year_validated` | EURUSD 15m 2018-2024 multi-year validation | Surviving reversal archetype. |
| `ny_impulse_mean_reversion` | event-combination strategies | `15m` | Large NY opening impulses may mean-revert after overreaction. | `walk_forward_validated` | EURUSD 15m 2018-2024 walk-forward | Strongest current event-combination branch. |
| `asian_range_compression_breakout` | event-combination strategies | `15m` | Compressed Asian ranges may expand directionally during London. | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Family frozen. |
| `atr_spike_new_high_low` | event-combination strategies | `15m` | ATR spikes plus fresh extremes may signal short-term continuation. | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Family frozen. |
| `compression_breakout` | event-combination strategies | `15m` | Compression followed by breakout may create tradeable expansion. | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Family frozen. |
| `compression_breakout_continuation` | event-combination strategies | `15m` | Strong breakout closes after compression may continue further. | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Family frozen. |
| `volatility_expansion_after_compression` | event-combination strategies | `15m` | Low-volatility regimes may transition into tradeable expansion. | `rejected` | EURUSD 15m 2018-2024 diagnostic + MVP tests | Family frozen. |
| `london_open_impulse_fade` | session reversal / sweep reversal | `15m` | Opening impulse at London may overextend and fade. | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Session-open fade family frozen. |
| `impulse_session_open` | event-combination strategies | `15m` | Early session impulse may continue directionally through the open. | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Session-open family frozen. |
| `vwap_intraday_reversion` | VWAP / midpoint mean reversion | `15m` | Large intraday VWAP deviation may mean-revert. | `rejected` | EURUSD 15m 2018-2024 MVP analysis | VWAP family frozen. |
| `vwap_session_open` | VWAP / midpoint mean reversion | `15m` | Extreme session-open VWAP deviation may revert intraday. | `rejected` | EURUSD 15m 2018-2024 smoke backtest | VWAP family frozen. |
| `head_shoulders_reversal` | pattern-based reversal | `15m` | Head-and-shoulders patterns may predict intraday reversal. | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Pattern family frozen. |
| `trend_exhaustion_reversal` | pattern-based reversal | `15m` | Sharp short-term impulses may exhaust and reverse. | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Pattern family frozen. |
| `tsmom_ma_cross` | trend / momentum | `1d` | Medium-horizon directional persistence may be captured by MA crossovers. | `rejected` | EURUSD 1d 2018-2024 walk-forward; GBPUSD spot check | Trend archetype remains active, but this config failed current gates. |
| `tsmom_donchian` | trend / momentum | `1d` | Daily breakouts beyond trailing highs/lows may persist. | `rejected` | EURUSD 1d 2018-2024 walk-forward | Trend archetype remains active, but this variant was too sparse. |
| `tsmom_return_sign` | trend / momentum | `1d` | Positive/negative trailing returns may predict continued direction. | `rejected` | EURUSD 1d 2018-2024 walk-forward; GBPUSD spot check | Trend archetype remains active, but this config failed drawdown/concentration gates. |

### Historical Diagnostic Branches

| strategy | archetype | timeframe | hypothesis | current status | last evaluation dataset | notes |
|---|---|---|---|---|---|---|
| `london_range_breakout` | session breakout continuation | `15m` | London opening range breaks may continue directionally. | `diagnostic` | EURUSD 15m 2018-2024 diagnostics | Historical continuation reference, not a live branch. |
| `session_breakout_continuation` | session breakout continuation | `15m` | Session breakout research may contain a durable continuation edge. | `diagnostic` | EURUSD 15m 2018-2024 mapping doc | Archetype mapping document only. |
| `asian_range_breakout` | session breakout continuation | `15m` | Asian range escape may drive London follow-through. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Rejected early breakout branch. |
| `filtered_london_breakout` | session breakout continuation | `15m` | ATR and range filters may improve London breakout quality. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Filter layering did not justify a separate branch. |
| `break_retest_continuation` | session breakout continuation | `15m` | Break-retest structures may continue after acceptance. | `rejected` | EURUSD 15m 2018-2024 diagnostics | One-off continuation diagnostic. |
| `asia_drift_london_reversal` | session reversal / sweep reversal | `15m` | Asian directional drift may reverse during London. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Transition-reversal branch frozen. |
| `london_impulse_ny_reversal` | session reversal / sweep reversal | `15m` | London impulse may mean-revert into New York. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Includes the rejected London-open fade line. |
| `liquidity_sweep_reversal` | session reversal / sweep reversal | `15m` | Sweeps beyond local highs/lows may reverse after trapped flow. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Generic sweep branch frozen. |
| `session_liquidity_sweep_reversal` | session reversal / sweep reversal | `15m` | Session-specific liquidity sweeps may revert intraday. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Frozen. |
| `ny_liquidity_sweep_reversal` | session reversal / sweep reversal | `15m` | New York sweeps may trap breakout traders and revert. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Frozen. |
| `session_vwap_reversion` | VWAP / midpoint mean reversion | `15m` | Session VWAP deviations may mean-revert. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Frozen with the VWAP tree. |
| `vwap_band_reversion_filtered` | VWAP / midpoint mean reversion | `15m` | Filtered VWAP-band deviations may improve reversion quality. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Frozen with the VWAP tree. |
| `range_midpoint_reversion` | VWAP / midpoint mean reversion | `15m` | Intraday range midpoint may attract price back after extension. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Frozen with the midpoint/VWAP tree. |
| `double_top_bottom_reversal` | pattern-based reversal | `15m` | Double-top and double-bottom shapes may signal intraday reversal. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Pattern family frozen. |
| `cup_handle_breakout` | pattern-based reversal | `15m` | Cup-and-handle breakout shape may predict continuation. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Pattern family frozen. |
| `double_impulse_exhaustion` | pattern-based reversal | `15m` | Repeated impulse bursts may signal exhaustion and reversal. | `rejected` | EURUSD 15m 2018-2024 diagnostics | Pattern family frozen. |
| `daily_extreme_move_reversal` | experimental / one-off | `1d diagnostic` | Large daily moves may mean-revert over the next 1-3 days. | `rejected` | EURUSD 15m 2018-2024 aggregated-to-daily diagnostic | Historical note only. |
| `multi_day_momentum_continuation` | trend / momentum | `1d diagnostic` | Large daily directional moves may continue across several days. | `rejected` | EURUSD 15m 2018-2024 aggregated-to-daily diagnostic | Superseded by the formal Phase 2 trend family. |
