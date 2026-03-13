# Strategy Matrix Status

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

| strategy_name | family | status | evidence | documentation_path | outputs_path | short_conclusion |
|---|---|---|---|---|---|---|
| asia_drift_london_reversal | session mean reversion | rejected | diagnostic | docs/strategy_asia_drift_london_reversal.md | outputs/asia_drift_london_reversal_diagnostic/ | researched and rejected |
| asian_range_breakout | session breakout | rejected | diagnostic | docs/strategy_asian_range_breakout.md | outputs/asian_range_breakout_diagnostic/ | marginal edge disappears under stress |
| asian_range_compression_breakout | volatility breakout | rejected | mvp_tested | docs/strategy_asian_range_compression_breakout.md | outputs/asian_range_compression_breakout_smoke/ | compression breakout MVP not strong enough to promote |
| atr_spike_new_high_low | volatility spike breakout | rejected | mvp_tested | docs/strategy_atr_spike_new_high_low.md | outputs/atr_spike_new_high_low_smoke/ | high turnover with PF below 1 |
| break_retest_continuation | market structure continuation | rejected | diagnostic | docs/strategy_break_retest_continuation.md | outputs/break_retest_continuation_diagnostic/ | researched and rejected |
| compression_breakout | volatility regime breakout | rejected | mvp_tested | docs/strategy_volatility_expansion_after_compression.md | outputs/compression_breakout_smoke/ | alternative breakout variant failed |
| compression_breakout_continuation | volatility regime breakout | rejected | mvp_tested | docs/strategy_volatility_expansion_after_compression.md | outputs/compression_breakout_continuation_smoke/ | stronger confirmation did not help |
| cup_handle_breakout | chart pattern breakout continuation | rejected | diagnostic | docs/strategy_cup_handle_breakout.md | outputs/cup_handle_breakout_diagnostic/ | researched and rejected |
| daily_extreme_move_reversal | multi-day mean reversion | rejected | diagnostic | docs/strategy_daily_extreme_move_reversal.md | outputs/daily_extreme_move_reversal_diagnostic/ | researched and rejected |
| double_impulse_exhaustion | impulse exhaustion mean reversion | rejected | diagnostic | docs/strategy_double_impulse_exhaustion.md | outputs/double_impulse_exhaustion_diagnostic/ | researched and rejected |
| double_top_bottom_reversal | chart pattern reversal | rejected | diagnostic | docs/strategy_double_top_bottom_reversal.md | outputs/double_top_bottom_reversal_diagnostic/ | researched and rejected |
| false_breakout_reversal | failed breakout reversal | rejected | multi_year_validated | docs/strategy_false_breakout_reversal.md | outputs/false_breakout_reversal_diagnostic/ | multi-year diagnostics exist, but current form is not promoted |
| filtered_london_breakout | session breakout continuation | diagnostic | diagnostic | docs/strategy_filtered_london_breakout.md | outputs/filtered_london_breakout_diagnostic/ | useful research branch, not a promoted strategy |
| head_shoulders_reversal | chart pattern reversal | rejected | mvp_tested | docs/strategy_head_shoulders_reversal.md | outputs/head_shoulders_reversal_smoke/ | classical pattern MVP failed clearly |
| impulse_session_open | session momentum continuation | rejected | mvp_tested | docs/strategy_impulse_session_open.md | outputs/impulse_session_open_smoke/ | high trade count, weak expectancy |
| liquidity_sweep_reversal | liquidity pattern / mean reversion | rejected | diagnostic | docs/strategy_liquidity_sweep_reversal.md | outputs/liquidity_sweep_reversal_diagnostic/ | researched and rejected |
| london_impulse_ny_reversal | session transition mean reversion | rejected | diagnostic | docs/strategy_london_impulse_ny_reversal.md | outputs/london_impulse_ny_reversal_diagnostic/ | researched and rejected |
| london_open_impulse_fade | session transition mean reversion | rejected | mvp_tested | docs/strategy_london_impulse_ny_reversal.md | outputs/london_open_impulse_fade_smoke/ | London-open fade remained negative |
| london_pullback_continuation | intraday continuation | diagnostic | mvp_tested | docs/strategy_london_pullback_continuation.md | outputs/london_pullback_continuation_analysis/ | worth consolidation, not yet promoted |
| london_range_breakout | session breakout continuation | diagnostic | diagnostic | docs/strategy_london_range_breakout.md | outputs/london_range_breakout_diagnostic/ | useful continuation research, not promoted |
| multi_day_momentum_continuation | medium-horizon momentum | diagnostic | diagnostic | docs/strategy_multi_day_momentum_continuation.md | outputs/multi_day_momentum_continuation_diagnostic/ | research exists; durable trend family still needs a proper MVP |
| ny_impulse_mean_reversion | event-driven mean reversion | candidate | walk_forward_validated | docs/strategy_ny_impulse_mean_reversion.md | outputs/ny_impulse_walkforward/ | strongest existing strategy family; still needs formal rerun and broader validation |
| ny_liquidity_sweep_reversal | session mean reversion | rejected | diagnostic | docs/strategy_ny_liquidity_sweep_reversal.md | outputs/ny_liquidity_sweep_reversal_diagnostic/ | researched and rejected |
| range_midpoint_reversion | session mean reversion | rejected | diagnostic | docs/strategy_range_midpoint_reversion.md | outputs/range_midpoint_reversion_diagnostic/ | researched and rejected |
| session_breakout_continuation | intraday continuation | diagnostic | diagnostic | docs/strategy_session_breakout_continuation.md | outputs/london_range_breakout_diagnostic/ | archetype retained for future consolidation |
| session_liquidity_sweep_reversal | liquidity reversal | rejected | diagnostic | docs/strategy_session_liquidity_sweep_reversal.md | outputs/session_liquidity_sweep_reversal_diagnostic/ | researched and rejected |
| session_vwap_reversion | intraday mean reversion | rejected | diagnostic | docs/strategy_session_vwap_reversion.md | outputs/session_vwap_reversion_diagnostic/ | researched and rejected |
| trend_exhaustion_reversal | trend exhaustion reversal | rejected | mvp_tested | docs/strategy_trend_exhaustion_reversal.md | outputs/trend_exhaustion_reversal_smoke/ | reversal-style trend exhaustion did not survive testing |
| volatility_expansion_after_compression | volatility regime | rejected | mvp_tested | docs/strategy_volatility_expansion_after_compression.md | outputs/volatility_expansion_after_compression_diagnostic/ | broad family investigated; current implementations rejected |
| vwap_band_reversion_filtered | intraday mean reversion | diagnostic | diagnostic | docs/strategy_vwap_band_reversion_filtered.md | outputs/vwap_intraday_reversion_diagnostic/ | already researched and should stay frozen until stronger evidence appears |
| vwap_intraday_reversion | intraday mean reversion | rejected | mvp_tested | docs/strategy_vwap_intraday_reversion.md | outputs/vwap_intraday_reversion_diagnostic/ | near break-even in places, still not promotable |
| vwap_session_open | session mean reversion | rejected | mvp_tested | docs/strategy_vwap_session_open.md | outputs/vwap_session_open_smoke/ | session-open fade remains rejected |
