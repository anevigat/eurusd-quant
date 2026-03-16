# H1 Downside Continuation MVP

## 1. Scope

Experiments implemented:

- `EXP_H1A_01`
- `EXP_H1A_02`
- `EXP_H1B_01`

Pairs:

- `EURUSD`
- `GBPUSD`

This branch implemented only the post-reset `H1` downside continuation family. `H2` and `H3` were left out intentionally.

## 2. Implementation Summary

Code added:

- one shared strategy module: `src/eurusd_quant/strategies/h1_downside_continuation.py`
- three experiment-specific config / registry aliases:
  - `h1_downside_continuation_exp_h1a_01`
  - `h1_downside_continuation_exp_h1a_02`
  - `h1_downside_continuation_exp_h1b_01`

Shared family logic:

- downside-only structural breach detection
- `London` or `early New York` context gating
- `strongly_expanded` session gating using trailing same-session ranges
- downside `breakout_low` / `sweep_low` routing
- online magnitude-bucket classification from prior breach history
- fixed `h4` holding horizon through `max_holding_bars = 16`

Locked vs open elements:

- locked from reset: session context, downside breach direction, event family, `h4` horizon, `EURUSD|GBPUSD` scope
- open in this branch: only the `H1A` entry timing difference between breach-bar entry and one-bar confirmation

## 3. Validation Sequence

Stages run:

- logic test
- smoke backtest
- focused sweep
- walk-forward validation
- cost stress
- pair robustness

Artifact roots:

- smoke: `outputs/post_reset_h1_smoke/`
- focused sweep: `outputs/post_reset_h1_sweeps/`
- walk-forward: `outputs/post_reset_h1_walk_forward/`

Key summaries:

- `outputs/post_reset_h1_smoke/smoke_summary.csv`
- `outputs/post_reset_h1_sweeps/focused_sweep_summary.csv`
- `outputs/post_reset_h1_walk_forward/walk_forward_summary.csv`
- `outputs/post_reset_h1_walk_forward/pair_robustness_summary.csv`

## 4. Results

### Smoke Backtests

`EXP_H1A_01`

- `EURUSD`: `195` trades, `PF 0.9826`, `net_pnl -0.00261`
- `GBPUSD`: `215` trades, `PF 1.0023`, `net_pnl 0.00060`
- interpretation: baseline breach-close variant was the least bad in sample and the only branch close to neutral on both pairs

`EXP_H1A_02`

- `EURUSD`: `104` trades, `PF 0.9035`, `net_pnl -0.00747`
- `GBPUSD`: `122` trades, `PF 0.9516`, `net_pnl -0.00688`
- interpretation: one-bar confirmation weakened the family immediately

`EXP_H1B_01`

- `EURUSD`: `157` trades, `PF 0.8911`, `net_pnl -0.00910`
- `GBPUSD`: `163` trades, `PF 0.9906`, `net_pnl -0.00117`
- interpretation: early-New-York sweep continuation stayed weak in sample, though less badly on `GBPUSD`

### Focused Sweep

The focused sweep was exactly the R10-bounded entry-style comparison:

- `EXP_H1A_01`: breach-bar entry
- `EXP_H1A_02`: one-bar confirmation

Result:

- `EXP_H1A_01` dominated `EXP_H1A_02` on both pairs
- `EXP_H1A_02` is a clean reject; the small allowed variation already broke the effect

`EXP_H1B_01` had no extra open dimension in R10, so the baseline run served as its focused-sweep evaluation.

### Walk-Forward Validation

`EXP_H1A_01`

- `EURUSD`: `66` OOS trades, `PF 1.4658`, `expectancy 0.000333`, stress survived, rejected for thin sample
- `GBPUSD`: `87` OOS trades, `PF 1.3898`, `expectancy 0.000401`, stress survived, rejected for thin sample plus yearly concentration and drawdown
- verdict: strongest branch in OOS terms, but still below the promotion floor

`EXP_H1A_02`

- `EURUSD`: `35` OOS trades, `PF 1.0004`, near-flat expectancy, rejected
- `GBPUSD`: `50` OOS trades, `PF 0.7446`, negative expectancy, failed stress, rejected
- verdict: confirmation variant is not credible

`EXP_H1B_01`

- `EURUSD`: `79` OOS trades, `PF 1.0573`, expectancy barely positive, rejected
- `GBPUSD`: `71` OOS trades, `PF 1.4541`, positive expectancy, stress survived, rejected for thin sample
- verdict: better than smoke implied, but still far below promotion standards

### Cost Stress

`EXP_H1A_01`

- both pairs survived stressed and harsh assumptions
- rejection was still unavoidable because trade density stayed far below the Phase 1 bar

`EXP_H1A_02`

- `GBPUSD` failed stressed and harsh assumptions outright
- `EURUSD` was effectively neutral and turned slightly negative under stress

`EXP_H1B_01`

- both pairs survived cost stress
- the branch still failed on trade count, and `EURUSD` also failed the profit-factor bar

### Pair Robustness

`EXP_H1A_01`

- pair agreement: `aligned_positive` in walk-forward
- problem: both pairs were still too thin, and `GBPUSD` was too concentrated in one year

`EXP_H1A_02`

- pair agreement: `contradictory`
- clean fast rejection under the R10 rules

`EXP_H1B_01`

- pair agreement: `aligned_positive`
- problem: both pairs stayed far below the required OOS trade density

## 5. Conclusions

Strongest experiment:

- `EXP_H1A_01`

Branch verdict:

- the `H1` family does show some post-reset structural signal in `walk_forward`, especially in `EXP_H1A_01`
- that signal is still too thin to survive the current Phase 1 promotion bar
- `EXP_H1A_02` should be treated as rejected immediately
- `EXP_H1B_01` is more interesting than its smoke run suggested, but it is still rejected in current form

Next-step implication:

- do not implement `H2` yet
- the honest outcome of this branch is that more research is needed before opening the next implementation family
