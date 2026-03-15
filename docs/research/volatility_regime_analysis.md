# Volatility Regime Analysis

## 1. Scope

Pairs analyzed:

- `EURUSD`
- `GBPUSD`
- `USDJPY`

Timeframe:

- `15m` bars aggregated into session records

Sample period:

- `2018-01-01 22:00:00+00:00` through `2024-12-31 21:45:00+00:00`

Timestamp and session conventions:

- UTC bar-open timestamps
- FX trading date anchored to the repo's `22:00 UTC` rollover
- session windows reused from R2:
  - `asia`: `00:00-07:00 UTC`
  - `london`: `07:00-13:00 UTC`
  - `new_york`: `13:00-24:00 UTC`

Volatility regime definition:

- primary metric: session realized volatility, computed as the standard deviation of `15m` close-to-close returns within each session
- regime assignment is computed per pair independently
- time-aware trailing lookback: `120` prior sessions
- minimum history before non-unknown labeling: `30` prior sessions
- quantile buckets:
  - `low_vol`: current realized volatility at or below the trailing 33rd percentile
  - `medium_vol`: between the 33rd and 67th percentiles
  - `high_vol`: at or above the trailing 67th percentile

Forward return horizons:

- `+1`, `+2`, `+4`, and `+8` session steps

Outputs:

- `outputs/diagnostics/volatility_regimes/regime_summary_by_pair.csv`
- `outputs/diagnostics/volatility_regimes/regime_persistence_summary.csv`
- `outputs/diagnostics/volatility_regimes/regime_transition_matrix.csv`
- `outputs/diagnostics/volatility_regimes/conditional_forward_returns_by_regime.csv`
- `outputs/diagnostics/volatility_regimes/session_behavior_by_regime.csv`
- `outputs/diagnostics/volatility_regimes/session_regime_transition_summary.csv`
- `outputs/diagnostics/volatility_regimes/volatility_regime_notes.json`

## 2. Basic Regime Descriptives

Cross-pair regime summary:

- volatility mainly changes movement magnitude, not raw signed return quality
- pooled `avg_range` rises from `0.002744` in `low_vol` to `0.006574` in `high_vol`
- pooled `avg_abs_return` rises from `0.001411` to `0.003503`
- pooled `avg_signed_return` deteriorates from `0.000205` in `low_vol` to `-0.000269` in `high_vol`

Directional structure changes only modestly:

- pooled directional efficiency increases from `0.2101` in `low_vol` to `0.2229` in `high_vol`
- pooled CLV falls from `0.5241` in `low_vol` to `0.4978` in `high_vol`

Pair differences:

- `EURUSD` is weak on signed return in all three regimes:
  - `low_vol`: `0.000015`
  - `medium_vol`: `-0.000103`
  - `high_vol`: `-0.000142`
- `GBPUSD` behaves similarly:
  - `low_vol`: `0.000069`
  - `medium_vol`: `-0.000013`
  - `high_vol`: `-0.000237`
- `USDJPY` remains structurally different:
  - `low_vol`: `0.000527`
  - `medium_vol`: `0.000292`
  - `high_vol`: `-0.000431`

Interpretation:

- high volatility clearly means larger sessions
- it does not automatically mean a better directional state
- `USDJPY` still carries more positive-close structure than the European pairs in low and medium volatility states

## 3. Regime Persistence

This phase adds the persistence layer that R2 did not cover.

Pooled persistence:

- `high_vol` is the most persistent regime:
  - persistence probability `0.3937`
  - average run length `1.65` sessions
- `low_vol` persistence probability is `0.3584`
- `medium_vol` is the least persistent state:
  - persistence probability `0.3148`
  - average run length `1.46` sessions

Pair differences are substantial:

- `USDJPY` volatility states cluster much more strongly than the other pairs:
  - `low_vol` persistence `0.5440`
  - `high_vol` persistence `0.5134`
  - average low-vol run length `2.19` sessions
  - average high-vol run length `2.05` sessions
- `EURUSD` and `GBPUSD` are much less stable:
  - `EURUSD low_vol`: `0.2630`
  - `GBPUSD low_vol`: `0.2660`
  - `EURUSD high_vol`: `0.3326`
  - `GBPUSD high_vol`: `0.3379`

Interpretation:

- `USDJPY` is the clearest volatility-clustering pair in this sample
- `EURUSD` and `GBPUSD` spend much less time staying in the same regime, especially in low volatility
- future continuation-style hypotheses should assume that regime persistence is pair-specific rather than generic

## 4. Conditional Forward Return Behavior

The forward-return analysis uses session-step horizons, not bars.

Pooled findings:

- high volatility mostly increases forward movement magnitude, not directional edge
- pooled `high_vol` mean forward return is close to flat at short horizons and slightly negative by `+8` sessions:
  - `+1`: `0.0000767`
  - `+2`: `0.0000671`
  - `+4`: `0.0000214`
  - `+8`: `-0.0000409`
- pooled `high_vol` mean absolute forward return is still the largest regime at every horizon

Low-volatility behavior is different:

- pooled `low_vol` is slightly negative at `+1`, then improves by longer horizons:
  - `+1`: `-0.0000946`
  - `+8`: `0.0002133`

Pair-specific differences matter more than pooled averages:

- `USDJPY high_vol` stays positive at every measured horizon:
  - `+1`: `0.000359`
  - `+2`: `0.000260`
  - `+4`: `0.000288`
  - `+8`: `0.000362`
- `USDJPY low_vol` starts slightly negative at `+1`, then becomes strongly positive by `+8` sessions:
  - `+1`: `-0.000125`
  - `+8`: `0.000882`
- `EURUSD` and `GBPUSD` do not show the same clean regime-conditioned directional profile

Interpretation:

- higher volatility reliably signals more movement, not cleaner directional carry
- the strongest directional behavior in this dataset is still pair-specific, especially in `USDJPY`
- any future regime-aware idea should distinguish between "more motion" and "more directional opportunity"

## 5. Regime x Session Interaction

R2 already showed that later sessions are wider and somewhat more directional. R3 confirms that this effect is heavily regime-dependent.

Pooled session-by-regime findings:

- `Asia low_vol`:
  - avg session return `0.000043`
  - continuation probability `0.5773`
- `Asia high_vol`:
  - avg session return `-0.000284`
  - continuation probability `0.5650`
- `London low_vol`:
  - avg session return `0.000257`
  - CLV `0.5472`
- `London high_vol`:
  - avg session return `-0.000152`
  - CLV `0.4960`
- `New York low_vol`:
  - avg session return `0.000529`
  - directional efficiency `0.2682`
  - CLV `0.5449`
- `New York high_vol`:
  - avg session return `-0.000435`
  - directional efficiency `0.2268`
  - CLV `0.4948`

What this adds beyond raw session summaries:

- high-vol London and New York sessions are wider, but their signed mean return is weaker, not stronger
- low-vol New York is the strongest pooled positive regime in the entire session x regime table
- continuation probabilities stay only mildly above 50 percent in most cells; the bigger effect is on movement magnitude and close placement

Pair-specific notes:

- `USDJPY` keeps a stronger positive-close bias than the other pairs even after conditioning
- `EURUSD` and `GBPUSD` both deteriorate noticeably in high-vol London and New York states

Interpretation:

- the headline later-session effects from R2 are not generic directional edges
- they are better understood as volatility-state-dependent changes in range, efficiency, and close placement

## 6. Regime Transitions Across Sessions

This phase also looked at how volatility state itself changes across major session boundaries.

### Asia -> London

Pooled transition behavior:

- after `low_vol` Asia, London becomes:
  - `low_vol` `18.1%`
  - `medium_vol` `35.5%`
  - `high_vol` `46.4%`
- after `medium_vol` Asia, London becomes `high_vol` `61.1%` of the time
- after `high_vol` Asia, London stays `high_vol` `75.0%` of the time

Interpretation:

- Asia-to-London is primarily an expansion boundary
- once Asia is already medium or high vol, London frequently inherits or amplifies that state

Pair differences:

- `EURUSD`: `high_vol Asia -> high_vol London` `87.9%`
- `GBPUSD`: `high_vol Asia -> high_vol London` `93.2%`
- `USDJPY`: `high_vol Asia -> high_vol London` `68.2%`

### London -> New York

This boundary is more balanced:

- after `low_vol` London, New York is:
  - `low_vol` `41.0%`
  - `medium_vol` `36.0%`
  - `high_vol` `23.0%`
- after `medium_vol` London, New York stays `medium_vol` `40.8%`
- after `high_vol` London, New York stays `high_vol` `42.3%`

Important caution:

- `high_vol London -> high_vol New York` is common, but the associated next-session mean return is still negative at `-0.000366`
- again, regime persistence is telling us more about future magnitude than about directional advantage

## 7. Research Implications

Main lessons from R3:

- volatility regime contains useful structural information, but mostly through magnitude, persistence, and transition behavior rather than clean directional drift
- `USDJPY` is the strongest candidate for future regime-aware structural work because its volatility states are more persistent and its forward-return profile is more asymmetric
- `EURUSD` and `GBPUSD` look less suited to naive "high-vol continuation" thinking; their high-vol states are wider but not directionally better
- London and New York effects should be conditioned on volatility regime in later research, because the raw session averages obscure meaningful internal differences
- Asia-to-London transition work should treat volatility expansion as the baseline expectation, not as an exceptional state

Guidance for later hypothesis generation:

- continuation studies should separate volatility clustering from actual directional edge
- regime-aware work should prioritize persistence and transition structure before turning descriptive effects into entry rules
- future cross-pair work should not assume that a regime effect observed in `USDJPY` transfers to `EURUSD` or `GBPUSD`

## 8. Limitations

- only `EURUSD`, `GBPUSD`, and `USDJPY` were included
- regime labels are descriptive percentile buckets, not statistically validated latent states
- no multiple-testing or formal significance layer has been applied yet
- the analysis is descriptive and should not be treated as tradable evidence by itself
