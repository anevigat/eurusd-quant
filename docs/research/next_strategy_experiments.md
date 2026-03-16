# Next Strategy Experiments

## 1. Scope

R10 converts the narrow `R9` hypothesis set into a controlled implementation plan for the next coding cycle.

This phase does not implement strategies. It defines:

- which experiments should be built first
- which structural elements are locked from `R8` and `R9`
- which execution elements may still be tested lightly
- which validation stages every experiment must pass
- when an experiment should be rejected quickly

Pairs in scope:

- `EURUSD`
- `GBPUSD`
- `USDJPY`

Priority remains explicit:

- `Tier 1`: `H1A`, `H1B`
- `Tier 2`: `H2`
- `Tier 3`: `H3`

## 2. Why The Experiment Count Is Intentionally Small

The reset eliminated most of the earlier research tree. Reopening a large experiment grid here would repeat the same failure mode.

R10 therefore plans only four active experiments plus one deferred placeholder:

- `EXP_H1A_01`
- `EXP_H1A_02`
- `EXP_H1B_01`
- `EXP_H2_01`
- `EXP_H3_01` as deferred only

The main path is the pooled European downside continuation family. The `USDJPY` upside branch stays secondary and pair-specific. The `H3` side case stays deferred unless the primary branches survive cleanly.

## 3. Experiment Plan By Hypothesis

### H1A

Primary design:

- `experiment_id`: `EXP_H1A_01`
- `pair_scope`: `EURUSD|GBPUSD`
- `session_context`: `London`
- `structural_condition`: `strongly_expanded` downside `breakout_low|sweep_low`
- `directionality_assumption`: continuation
- `entry_style`: breach bar close
- `exit_style`: fixed `h4` horizon

Bounded variant:

- `experiment_id`: `EXP_H1A_02`
- same structural condition as `EXP_H1A_01`
- only change: one-bar confirmation entry

Locked elements from reset evidence:

- session must be `London`
- range regime must be `strongly_expanded`
- breach direction must be downside
- breach family stays `breakout_low|sweep_low`
- evaluation horizon stays `h4`

Open elements allowed for light testing:

- breach-close entry vs one-bar confirmation
- no more than one minimal execution-timing variant beyond the baseline

Fast rejection emphasis:

- reject if the breach-close baseline is clearly negative after costs
- reject if the one-bar confirmation variant flips the sign or collapses sample count
- reject if `EURUSD` and `GBPUSD` point in opposite directions once reported separately

### H1B

Primary design:

- `experiment_id`: `EXP_H1B_01`
- `pair_scope`: `EURUSD|GBPUSD`
- `session_context`: `early New York`
- `structural_condition`: `strongly_expanded` downside `sweep_low`
- `directionality_assumption`: continuation
- `entry_style`: breach bar close
- `exit_style`: fixed `h4` horizon

Locked elements from reset evidence:

- session must remain `early New York`
- condition must remain `sweep_low`
- range regime must remain `strongly_expanded`
- breach direction remains downside
- horizon remains `h4`

Open elements allowed for light testing:

- at most one later exit comparison if the baseline survives
- no extra context filters beyond those already implied by the hypothesis family

Fast rejection emphasis:

- reject if the strategy becomes mostly magnitude with no usable directional edge
- reject if cost stress immediately flips the sign
- reject if the edge vanishes once `EURUSD` and `GBPUSD` are reported separately

### H2

Primary design:

- `experiment_id`: `EXP_H2_01`
- `pair_scope`: `USDJPY`
- `session_context`: `New York`
- `structural_condition`: `strongly_expanded` upside `breakout_high`
- `directionality_assumption`: continuation
- `entry_style`: breach bar close
- `exit_style`: fixed `h4` horizon

Locked elements from reset evidence:

- pair must remain `USDJPY`
- session must remain `New York`
- breach type stays `breakout_high`
- breach direction remains upside
- magnitude bucket remains `small`
- horizon remains `h4`

Open elements allowed for light testing:

- only a narrow timing sensitivity check
- no pooled inference with `EURUSD` or `GBPUSD`

Fast rejection emphasis:

- reject if pair-specific sensitivity checks erase the effect
- reject if the baseline turns into a one-horizon artifact
- reject if friction sanity makes the effect too small to matter

### H3

Status:

- `experiment_id`: `EXP_H3_01`
- `status`: `deferred`

Decision:

- no immediate implementation budget
- only revisit if `H1A`, `H1B`, and `H2` fail cleanly or if later evidence materially improves the side case

This prevents `Tier 3` curiosity from consuming equal effort.

## 4. Validation Ladder

All experiments use the same validation ladder so results remain comparable.

### Stage 1: Logic Test

- required outputs: `unit_test_results`
- required metrics: pass/fail, test count
- purpose: validate deterministic event detection, sign normalization, and session/regime gating

### Stage 2: Smoke Backtest

- required outputs: `metrics.json`, `equity_curve.csv`, `trades.parquet`
- required metrics: `net_pnl`, `trade_count`, `profit_factor`, `max_drawdown`
- purpose: confirm the experiment runs end-to-end on the intended pair scope

### Stage 3: Focused Sweep

- required outputs: `top_configs.csv`, `sweep_metrics.csv`
- required metrics: `net_pnl`, `profit_factor`, `expectancy`, `trade_count`
- purpose: test only the bounded execution alternatives allowed by the experiment

### Stage 4: Walk-Forward

- required outputs: `splits.csv`, `aggregate.json`, `promotion_report.json`
- required metrics: `oos_profit_factor`, `oos_expectancy`, `oos_trade_count`, yearly breakdown
- purpose: apply the shared Phase 1 walk-forward protocol

### Stage 5: Cost Stress

- required outputs: `cost_stress_summary.csv`
- required metrics: baseline vs stressed `profit_factor` and `net_pnl`
- purpose: confirm the effect does not disappear under modest friction increases

### Stage 6: Robustness

- required outputs: `robustness_summary.csv`
- required metrics: pair breakdown, parameter neighborhood, stability flags
- purpose:
  - for `H1A` and `H1B`: cross-pair robustness and contradiction checks
  - for `H2`: pair-specific sensitivity checks only

### Stage 7: Portfolio Check

- required outputs: `portfolio_comparison.json`
- required metrics: correlation, contribution, drawdown impact, return/drawdown ratio
- purpose: test only survivors for genuine portfolio relevance

## 5. Fast Rejection Rules

The next coding cycle should stop weak branches quickly.

Shared rejection rules:

- reject if full-sample `net_pnl` is clearly negative
- reject if realistic cost stress pushes `profit_factor` clearly below `1.0`
- reject if trade count is too low for meaningful walk-forward evaluation
- reject if one small execution variation removes the effect
- reject if walk-forward is negative or dominated by one year
- reject if pair pooling hides contradictory pair behavior
- reject if the branch adds no portfolio value after surviving earlier stages

Experiment-specific emphasis:

- `H1A`: reject if London downside continuation only exists in one of `EURUSD` or `GBPUSD`
- `H1B`: reject if early-New-York downside behavior is not directionally better than generic expanded-breach noise
- `H2`: reject if `USDJPY` does not remain cleaner than pooled alternatives under pair-specific robustness checks
- `H3`: defer rather than rescue

## 6. Comparability Rules

To avoid biased comparisons, all experiments must share:

- the same session and timestamp conventions from the reset phases
- the same base transaction-cost assumptions
- the same walk-forward protocol
- the same reporting metrics
- the same output layout under `outputs/`
- the same promotion framework from Phase 1

No experiment gets extra filtering freedom unless that freedom is stated up front in the experiment catalog.

## 7. Expected Outputs For The Next Implementation Cycle

Each implemented experiment should produce:

- deterministic strategy tests
- smoke-backtest metrics and trade artifacts
- one bounded focused sweep
- walk-forward artifacts
- cost-stress summary
- robustness summary
- portfolio comparison only if prior stages survive

Expected output roots:

- `outputs/strategy_experiments/<experiment_id>/backtest/`
- `outputs/strategy_experiments/<experiment_id>/sweep/`
- `outputs/strategy_experiments/<experiment_id>/walk_forward/`
- `outputs/strategy_experiments/<experiment_id>/robustness/`

## 8. Main Vs Secondary Path

The implementation order should remain:

1. `EXP_H1A_01`
2. `EXP_H1A_02`
3. `EXP_H1B_01`
4. `EXP_H2_01`
5. `EXP_H3_01` only if explicitly revived later

This keeps the main path on pooled downside continuation rather than letting the `USDJPY` branch or the side case dominate the roadmap.

## 9. Limitations

R10 is only a planning phase.

- none of these experiments are validated yet
- candidate conditions still come from descriptive research rather than implemented systems
- pair pooling may still hide nuance
- later strategy branches must not widen the search space beyond the locked conditions documented here
