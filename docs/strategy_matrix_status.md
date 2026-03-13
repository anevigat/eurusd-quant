# Strategy Matrix Status

| strategy_name | family | status | documentation_path | outputs_path | short_conclusion |
|---|---|---|---|---|---|
| asia_drift_london_reversal | session mean reversion | diagnostic_complete_rejected | docs/strategy_asia_drift_london_reversal.md | outputs/asia_drift_london_reversal_diagnostic/ | researched_but_not_promising |
| session_liquidity_sweep_reversal | liquidity pattern | diagnostic_complete_rejected | docs/strategy_session_liquidity_sweep_reversal.md | outputs/session_liquidity_sweep_reversal_diagnostic/ | researched_but_not_promising |
| ny_liquidity_sweep_reversal | session mean reversion | diagnostic_complete_rejected | docs/strategy_ny_liquidity_sweep_reversal.md | outputs/ny_liquidity_sweep_reversal_diagnostic/ | researched_but_not_promising |
| liquidity_sweep_reversal | liquidity pattern / mean reversion | diagnostic_complete_rejected | docs/strategy_liquidity_sweep_reversal.md | outputs/liquidity_sweep_reversal_diagnostic/ | researched_but_not_promising |
| london_impulse_ny_reversal | session transition mean reversion | diagnostic_complete_rejected | docs/strategy_london_impulse_ny_reversal.md | outputs/london_impulse_ny_reversal_diagnostic/ | researched_but_not_promising |
| london_open_impulse_fade | session transition mean reversion | mvp_implemented_rejected | docs/strategy_london_impulse_ny_reversal.md | outputs/london_open_impulse_fade_smoke/ | London-open fade MVP had manageable drawdown but remained slightly negative (PF 0.86); rejected |
| impulse_session_open | session momentum continuation | mvp_implemented_rejected | docs/strategy_impulse_session_open.md | outputs/impulse_session_open_smoke/ | Session-open impulse continuation produced high trade count but PF 0.80 and negative PnL; rejected |
| double_impulse_exhaustion | impulse exhaustion / mean reversion | diagnostic_complete_rejected | docs/strategy_double_impulse_exhaustion.md | outputs/double_impulse_exhaustion_diagnostic/ | researched_but_not_promising |
| session_vwap_reversion | session mean reversion | diagnostic_complete_rejected | docs/strategy_session_vwap_reversion.md | outputs/session_vwap_reversion_diagnostic/ | researched_but_not_promising |
| double_top_bottom_reversal | chart pattern reversal | diagnostic_complete_rejected | docs/strategy_double_top_bottom_reversal.md | outputs/double_top_bottom_reversal_diagnostic/ | researched_but_not_promising |
| false_breakout_reversal | chart pattern failed breakout | diagnostic_complete_rejected | docs/strategy_false_breakout_reversal.md | outputs/false_breakout_reversal_diagnostic/ | researched_but_not_promising |
| trend_exhaustion_reversal | chart pattern exhaustion reversal | mvp_implemented_rejected | docs/strategy_trend_exhaustion_reversal.md | outputs/trend_exhaustion_reversal_smoke/ | MVP tested on 2018-2024; high trade count but PF<1 and deep drawdown; rejected |
| head_shoulders_reversal | chart pattern reversal | mvp_implemented_rejected | docs/strategy_head_shoulders_reversal.md | outputs/head_shoulders_reversal_smoke/ | MVP tested on 2018-2024; high turnover with PF<1 and very large drawdown; rejected |
| cup_handle_breakout | chart pattern breakout continuation | diagnostic_complete_rejected | docs/strategy_cup_handle_breakout.md | outputs/cup_handle_breakout_diagnostic/ | researched_but_not_promising |
| daily_extreme_move_reversal | multi-day mean reversion | diagnostic_complete_rejected | docs/strategy_daily_extreme_move_reversal.md | outputs/daily_extreme_move_reversal_diagnostic/ | researched_but_not_promising |
| range_midpoint_reversion | session mean reversion | diagnostic_complete_rejected | docs/strategy_range_midpoint_reversion.md | outputs/range_midpoint_reversion_diagnostic/ | researched_but_not_promising |
| volatility_expansion_after_compression | volatility regime | diagnostic_complete_rejected | docs/strategy_volatility_expansion_after_compression.md | outputs/volatility_expansion_after_compression_diagnostic/ | diagnostic looked promising; MVP failed clearly; current form rejected |
| compression_breakout | volatility regime breakout | mvp_implemented_rejected | docs/strategy_volatility_expansion_after_compression.md | outputs/compression_breakout_smoke/ | Alternative compression breakout MVP tested; PF 0.56 with negative PnL; rejected |
| compression_breakout_continuation | volatility regime breakout | mvp_implemented_rejected | docs/strategy_volatility_expansion_after_compression.md | outputs/compression_breakout_continuation_smoke/ | Stronger breakout confirmation reduced trades but remained clearly unprofitable (PF 0.52); rejected |
| break_retest_continuation | market structure | diagnostic_complete_rejected | docs/strategy_break_retest_continuation.md | outputs/break_retest_continuation_diagnostic/ | researched_but_not_promising |
| vwap_band_reversion_filtered | intraday mean reversion | already_researched | docs/strategy_vwap_band_reversion_filtered.md | outputs/vwap_intraday_reversion_diagnostic/ | already_researched |
| session_breakout_continuation | momentum | already_researched | docs/strategy_session_breakout_continuation.md | outputs/london_range_breakout_diagnostic/ | already_researched |
| multi_day_momentum_continuation | momentum | already_researched | docs/strategy_multi_day_momentum_continuation.md | outputs/multi_day_momentum_continuation_diagnostic/ | already_researched |
