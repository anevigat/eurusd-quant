# Strategy Matrix Status

Phase 5 tightened the candidate set further. The current view keeps only the sleeves that still have credible follow-up evidence and freezes the continuation branch until a materially different hypothesis appears.

- Strategies tracked: `36`
- Rejected / frozen strategies: `32`
- Candidate-or-better strategies: `2`
- Active archetypes: `3`
- Frozen families: `6`
- Phase 5 note: session-aligned trend revalidation and focused intraday reruns removed the continuation sleeve from the active candidate set.

## Active Archetypes

- `session reversal / sweep reversal`
- `event-combination strategies`
- `trend / momentum`

## Frozen Families

- `session breakout continuation`
- `session-open fades and impulse-open variants`
- `VWAP / midpoint mean reversion`
- `pattern-based reversals and exhaustion patterns`
- `compression / volatility breakout variants`
- `miscellaneous one-off diagnostics outside the surviving archetypes`

## Status Legend

| status | meaning |
|---|---|
| `idea` | not yet tested |
| `diagnostic` | researched or mapped, but not promoted to MVP |
| `mvp_tested` | coded and backtested, still below promotion quality |
| `rejected` | failed current promotion gates or clearly weaker than alternatives |
| `candidate` | worth further validation |
| `multi_year_validated` | passed broad multi-year checks |
| `walk_forward_validated` | passed rolling OOS validation |
| `cross_pair_validated` | acceptable across additional pairs |
| `paper_trade_candidate` | ready for paper trading once orchestration exists |
| `paper_trading` | actively paper traded |

## Current Matrix

Tracked rows below include both implemented code paths (`code`) and documented historical research branches (`doc`).

| strategy | impl | archetype | timeframe | status | last evaluation | notes |
|---|---|---|---|---|---|---|
| `session_breakout` | `code` | session breakout continuation | `15m` | `rejected` | EURUSD 15m 2018-2024 focused rerun + walk-forward | Even the best `07:00-08:00 UTC` + breakout-buffer refinement stayed negative in sample and OOS; freeze the continuation slot. |
| `london_pullback_continuation` | `code` | session breakout continuation | `15m` | `rejected` | EURUSD 15m 2018-2024 smoke + Phase 5 portfolio recheck | Old continuation survivor no longer deserves active status after repeated negative evidence and portfolio drag. |
| `london_range_breakout` | `doc` | session breakout continuation | `15m` | `diagnostic` | EURUSD 15m 2018-2024 diagnostics | Historical diagnostic branch kept as reference for the breakout archetype, not as a separate expansion path. |
| `session_breakout_continuation` | `doc` | session breakout continuation | `15m` | `diagnostic` | EURUSD 15m 2018-2024 research mapping | Archetype-level mapping doc; retained as reference, not as a license to keep spawning close variants. |
| `asian_range_breakout` | `doc` | session breakout continuation | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Original session breakout variant failed under costs and stays frozen. |
| `filtered_london_breakout` | `doc` | session breakout continuation | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Minor filtered variant of the same continuation tree; frozen to avoid branch proliferation. |
| `break_retest_continuation` | `doc` | session breakout continuation | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Structure-follow-through hypothesis did not justify a live branch. |
| `false_breakout_reversal` | `code` | session reversal / sweep reversal | `15m` | `multi_year_validated` | EURUSD 15m 2018-2024 multi-year validation | Surviving reversal archetype; keep this family active, but promotion still stops short of paper-trade status. |
| `asia_drift_london_reversal` | `doc` | session reversal / sweep reversal | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Session-transition fade did not hold up. |
| `london_impulse_ny_reversal` | `doc` | session reversal / sweep reversal | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Transition-reversal branch is frozen; includes the negative London-open fade MVP. |
| `london_open_impulse_fade` | `code` | session reversal / sweep reversal | `15m` | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Session-open fade variants are frozen. |
| `liquidity_sweep_reversal` | `doc` | session reversal / sweep reversal | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Generic sweep reversal branch stays frozen. |
| `session_liquidity_sweep_reversal` | `doc` | session reversal / sweep reversal | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Session-specific sweep variant did not earn a continued branch. |
| `ny_liquidity_sweep_reversal` | `doc` | session reversal / sweep reversal | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | NY sweep variant is frozen with the rest of the sweep-only tree. |
| `ny_impulse_mean_reversion` | `code` | event-combination strategies | `15m` | `candidate` | EURUSD 15m 2018-2024 threshold revalidation + walk-forward | Tightening the threshold to `22.0` pips improved PF and drawdown, but trade density and yearly concentration still fail formal promotion gates. |
| `impulse_session_open` | `code` | event-combination strategies | `15m` | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Session-open momentum variant is frozen with the rest of the open variants. |
| `atr_spike_new_high_low` | `code` | event-combination strategies | `15m` | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Multi-condition event combo did not survive first-pass testing. |
| `volatility_expansion_after_compression` | `code` | event-combination strategies | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostic + MVP tests | Family investigated broadly and frozen after repeated failure. |
| `compression_breakout` | `code` | event-combination strategies | `15m` | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Compression breakout variant is frozen. |
| `compression_breakout_continuation` | `code` | event-combination strategies | `15m` | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Stronger breakout confirmation did not rescue the family. |
| `asian_range_compression_breakout` | `code` | event-combination strategies | `15m` | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Compression-style London breakout did not justify continued expansion. |
| `vwap_intraday_reversion` | `code` | VWAP / midpoint mean reversion | `15m` | `rejected` | EURUSD 15m 2018-2024 MVP analysis | Near break-even in places, still not promotable; family frozen. |
| `session_vwap_reversion` | `doc` | VWAP / midpoint mean reversion | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Historical VWAP/session reversion branch; frozen. |
| `vwap_band_reversion_filtered` | `doc` | VWAP / midpoint mean reversion | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Filtering did not change the conclusion; frozen. |
| `vwap_session_open` | `code` | VWAP / midpoint mean reversion | `15m` | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Session-open VWAP fade is frozen. |
| `range_midpoint_reversion` | `doc` | VWAP / midpoint mean reversion | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Midpoint-reversion variant did not earn a live branch. |
| `head_shoulders_reversal` | `code` | pattern-based reversal | `15m` | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Classical pattern MVP failed clearly; pattern family frozen. |
| `double_top_bottom_reversal` | `doc` | pattern-based reversal | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Pattern-heavy reversal branch frozen. |
| `cup_handle_breakout` | `doc` | pattern-based reversal | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Chart-pattern continuation branch frozen with the pattern tree. |
| `trend_exhaustion_reversal` | `code` | pattern-based reversal | `15m` | `rejected` | EURUSD 15m 2018-2024 smoke backtest | Reversal-style exhaustion setup did not survive testing. |
| `double_impulse_exhaustion` | `doc` | pattern-based reversal | `15m` | `rejected` | EURUSD 15m 2018-2024 diagnostics | Exhaustion pattern branch frozen. |
| `daily_extreme_move_reversal` | `doc` | experimental / one-off | `1d diagnostic` | `rejected` | EURUSD 15m 2018-2024 aggregated-to-daily diagnostic | Useful exploratory note, not a live research branch. |
| `multi_day_momentum_continuation` | `doc` | trend / momentum | `1d diagnostic` | `rejected` | EURUSD 15m 2018-2024 aggregated-to-daily diagnostic | Early precursor to Phase 2; superseded by the formal trend family. |
| `tsmom_ma_cross` | `code` | trend / momentum | `1d` | `rejected` | EURUSD + GBPUSD 1d session-aligned walk-forward | Session-aware daily bars overturned the earlier exploratory GBPUSD strength; the narrow neighborhood now fails on both pairs. |
| `tsmom_donchian` | `code` | trend / momentum | `1d` | `rejected` | EURUSD 1d 2018-2024 walk-forward | Thin-sample breakout variant rejected in current form. |
| `tsmom_return_sign` | `code` | trend / momentum | `1d` | `rejected` | EURUSD 1d 2018-2024 walk-forward; GBPUSD spot check | Trend family remains active, but this variant still failed drawdown and concentration gates. |
