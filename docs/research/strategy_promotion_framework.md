# Strategy Promotion Framework

## Purpose

This repo should treat a "top config" from a sweep as a hypothesis, not as a deployment candidate. Promotion is the process that converts a research result into a repeatable, defensible candidate for paper trading.

## Status Definitions

| status | meaning |
|---|---|
| `idea` | hypothesis exists but has not been tested with code or data |
| `diagnostic` | research mapping or descriptive diagnostics exist, but the strategy is not yet an MVP candidate |
| `mvp_tested` | executable strategy exists and has been tested on a baseline dataset |
| `rejected` | the strategy failed promotion gates or was clearly dominated by better alternatives |
| `candidate` | the strategy is promising enough to justify deeper validation |
| `multi_year_validated` | multi-year testing exists and no single subperiod obviously invalidates the edge |
| `walk_forward_validated` | rolling OOS validation passed under the formal framework |
| `cross_pair_validated` | behavior remains acceptable on other major FX pairs |
| `paper_trade_candidate` | all required validation layers passed; eligible for paper trading |
| `paper_trading` | strategy is currently active in the paper-trading harness |

## Promotion Path

1. `idea`
2. `diagnostic`
3. `mvp_tested`
4. `candidate`
5. `multi_year_validated`
6. `walk_forward_validated`
7. `cross_pair_validated`
8. `paper_trade_candidate`
9. `paper_trading`

Any hard failure along the path moves the strategy to `rejected`.

## Minimum Promotion Gates

These gates are implemented in `src/eurusd_quant/validation/promotion.py` and should be treated as defaults, not immutable constants.

| gate | default threshold | notes |
|---|---|---|
| minimum total trades | `>= 200` | OOS total across all walk-forward splits |
| minimum trades per year | `>= 50` | for intraday strategies; lower-frequency systems should override |
| positive expectancy after costs | `> 0.0` | must be net of modeled slippage/spread/fees |
| OOS profit factor | `>= 1.10` | default promotion floor |
| max drawdown ceiling | `<= 0.02` | configurable ceiling in instrument price units |
| single-year PnL concentration | `<= 45%` | share of positive PnL from the best year |
| stressed-cost survival | `PF >= 1.0` and `expectancy > 0.0` | required under `stressed` and `harsh` scenarios |
| parameter neighborhood stability | `>= 3` neighbors and `>= 60%` pass rate | optional until adjacent sweep results exist |

## Walk-Forward Standard

The generic walk-forward engine lives in `src/eurusd_quant/validation/walk_forward.py` and supports:

- rolling train/test windows
- configurable train length in years
- configurable OOS window in months
- optional embargo in days
- aggregate OOS metrics only
- split-level output plus aggregate output
- cost-stress overlays on the OOS windows
- external promotion metadata passed through the CLI

The Phase 1 CLI now carries, but does not generate, extra promotion evidence:

- per-config `parameter_neighborhood_json` from sweep CSVs
- global promotion metadata via `--promotion-metadata-json`
- explicit cross-pair status via `--cross-pair-validated true|false`

Merge priority for promotion metadata is:

1. CLI defaults
2. metadata JSON file
3. per-config CSV row metadata

Per-config CSVs may include `parameter_neighborhood_json`. Current promotion logic expects a JSON object with the neighborhood fields it already evaluates, for example:

```json
{"evaluated_neighbors": 8, "passing_neighbors": 7, "pass_rate": 0.875}
```

Walk-forward results alone are sufficient to reach `walk_forward_validated`, but not `paper_trade_candidate`. That higher status still requires extra evidence, including cross-pair validation and a passing neighborhood stability gate.

Output convention:

- `outputs/walk_forward/<strategy>/<config_hash>/splits.csv`
- `outputs/walk_forward/<strategy>/<config_hash>/aggregate.json`
- `outputs/walk_forward/<strategy>/<config_hash>/equity_curve.csv`
- `outputs/walk_forward/<strategy>/<config_hash>/promotion_report.json`

## Cost Stress Standard

`src/eurusd_quant/validation/cost_stress.py` applies three cost regimes by default:

- `baseline`
- `stressed`: +25% spread/slippage/fees
- `harsh`: +50% spread/slippage/fees

The module also supports:

- explicit spread multipliers
- slippage adders in pips
- commission overrides

## Reporting Standard

Every promotion report should include:

- hypothesis
- exact rules
- dataset used
- IS/OOS ranges
- yearly metrics
- stressed-cost metrics
- pass/fail by gate
- decision: `reject`, `continue`, or `paper_trade_candidate`

Use `docs/templates/strategy_promotion_template.md` as the human-readable template and `scripts/generate_promotion_report.py` for markdown generation from walk-forward outputs.
