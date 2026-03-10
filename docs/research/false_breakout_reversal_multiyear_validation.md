# False Breakout Reversal Multi-Year Validation (2018-2024)

## Objective

Validate the current best candidate `false_breakout_reversal` configuration across multiple years without any parameter tuning.

This is a frozen-parameter robustness check, not an optimization pass.

## Frozen Configuration

Strategy:

- `strategy`: `false_breakout_reversal`
- `allowed_side`: `both`
- `entry_window_utc`: `08:00-09:00` (`[start, end)`)
- `exit_model`: `atr_target`

All other parameters come from `config/strategies.yaml` and were kept unchanged during this validation.

## Years Tested

- 2018
- 2019
- 2020
- 2021
- 2022
- 2023
- 2024

## How To Re-Run

```bash
.venv/bin/python scripts/run_false_breakout_multiyear_validation.py \
  --start-year 2018 \
  --end-year 2024 \
  --bars-dir data/bars/15m \
  --output-root outputs/experiments/false_breakout_reversal_atr_target_0809
```

## Output Locations

Root:

- `outputs/experiments/false_breakout_reversal_atr_target_0809/`

Per-year artifacts:

- `outputs/experiments/false_breakout_reversal_atr_target_0809/<year>/trades.parquet`
- `outputs/experiments/false_breakout_reversal_atr_target_0809/<year>/metrics.json`

Consolidated artifacts:

- `outputs/experiments/false_breakout_reversal_atr_target_0809/summary.csv`
- `outputs/experiments/false_breakout_reversal_atr_target_0809/monthly_pnl.csv`
- `outputs/experiments/false_breakout_reversal_atr_target_0809/run_metadata.json`

## Key Yearly Results

| year | trade_count | win_rate | profit_factor | net_pnl | expectancy | max_drawdown | average_win_pips | average_loss_pips |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2018 | 153 | 0.5948 | 0.8544 | -0.014764 | -0.000096 | 0.023595 | 9.5177 | -16.3509 |
| 2019 | 127 | 0.6378 | 1.0434 | 0.002046 | 0.000016 | 0.007658 | 6.0709 | -10.2453 |
| 2020 | 133 | 0.5940 | 0.7595 | -0.022736 | -0.000171 | 0.028868 | 9.0886 | -17.5065 |
| 2021 | 150 | 0.5733 | 0.8393 | -0.010902 | -0.000073 | 0.021637 | 6.6187 | -10.7655 |
| 2022 | 147 | 0.6190 | 1.1291 | 0.011431 | 0.000078 | 0.017673 | 10.9869 | -15.8125 |
| 2023 | 165 | 0.6424 | 1.1696 | 0.012263 | 0.000074 | 0.014346 | 7.9764 | -12.2520 |
| 2024 | 139 | 0.6475 | 1.2290 | 0.010273 | 0.000074 | 0.009369 | 6.1250 | -9.3441 |

## Aggregate Interpretation

- Positive years: `4 / 7` (2019, 2022, 2023, 2024)
- Negative years: `3 / 7` (2018, 2020, 2021)
- Combined net PnL across 2018-2024: `-0.012389`
- Total trades: `1014`

Interpretation:

- The configuration shows regime dependence: profitability appears in some recent years, but does not hold consistently across all years.
- This validation intentionally used frozen parameters and no new optimization, so observed instability reflects out-of-sample robustness limitations of the current setup.

## Notes

- No new filters were added.
- No strategy logic changes were made for performance reasons.
- No side segmentation or window re-optimization was performed in this validation.
