# Cross-Pair Robustness Testing

## Purpose

This batch evaluates whether the NY impulse mean-reversion edge is:

- stable across multiple FX pairs
- stable across both historical (`2018-2024`) and forward (`2025-now`) ranges
- concentrated in EURUSD only, or portable across pairs

The workflow is research-only and does not change execution, paper trading, or live trading.

## Pairs and Ranges

The sweep runner checks these files and auto-skips missing datasets:

- `EURUSD`, `GBPUSD`, `USDJPY`, `AUDUSD`
- `historical`: `*_bars_15m_2018_2024.parquet`
- `forward`: `*_bars_15m_2025_now.parquet`

Missing pair/range files are recorded in `summary.json` and do not fail the run.

## Sweep Parameters

The batch uses a focused NY-impulse grid:

- impulse threshold percentiles: `p85`, `p90`, `p95`
- entry retracement ratio: `0.40`, `0.50`, `0.60`
- exit model: `atr_1_0`, `atr_1_5`, `retracement_0_75`

Total per dataset: `3 * 3 * 3 = 27` configs.

Threshold labels are mapped to per-dataset NY impulse quantiles using the same impulse window (`13:00-13:30 UTC`) used by strategy research.

## Robustness Scoring

The robustness analyzer loads all pair/range sweep outputs and computes:

- best config per pair/range
- global config ranking across datasets
- robust config subset (multi-pair + historical pass + forward non-catastrophic)

Score:

`robustness_score = mean_profit_factor_across_pairs * log(total_trades_across_pairs + 1) * survival_factor`

Where:

- `historical_pass`: `profit_factor > 1.0` and `total_trades >= 100`
- `forward_noncat`: `profit_factor >= 0.95`
- `survival_factor = (0.5 + 0.5 * historical_pass_ratio) * (0.5 + 0.5 * forward_noncat_ratio)`

## Outputs

Sweep outputs:

- `outputs/cross_pair_sweeps/<pair>/<range>/experiment_results.csv`
- `outputs/cross_pair_sweeps/<pair>/<range>/top_configs.csv`
- `outputs/cross_pair_sweeps/<pair>/<range>/summary.json`
- `outputs/cross_pair_sweeps/summary.json`

Robustness aggregation outputs:

- `outputs/cross_pair_robustness/pair_best_configs.csv`
- `outputs/cross_pair_robustness/global_config_ranking.csv`
- `outputs/cross_pair_robustness/robust_configs.csv`
- `outputs/cross_pair_robustness/config_pair_pf_matrix.csv`
- `outputs/cross_pair_robustness/robustness_summary.json`

## Batch Results (Current Run)

Detected datasets:

- `EURUSD_historical`
- `EURUSD_forward`
- `GBPUSD_historical`
- `GBPUSD_forward`

Missing (auto-skipped):

- `USDJPY_historical`, `USDJPY_forward`
- `AUDUSD_historical`, `AUDUSD_forward`

Best config by pair/range:

- `EURUSD_historical`: `p85_entry_0.50_atr_1_5` (PF `1.3446`, trades `150`)
- `EURUSD_forward`: `p95_entry_0.60_atr_1_0` (PF `inf`, trades `4`, very small sample)
- `GBPUSD_historical`: `p85_entry_0.60_atr_1_5` (PF `0.9019`, trades `125`)
- `GBPUSD_forward`: `p85_entry_0.60_atr_1_0` (PF `0.9163`, trades `26`)

Top robust configs (multi-pair filtered):

1. `p85_entry_0.60_atr_1_5`
2. `p85_entry_0.60_retracement_0_75`
3. `p85_entry_0.60_atr_1_0`

Interpretation:

- EURUSD retains positive historical behavior for parts of the grid.
- GBPUSD is below PF `1.0` in both historical and forward ranges for this batch.
- Cross-pair robustness is currently weak/inconclusive because only two pairs are available and forward samples are short.
- Current evidence suggests the edge may be at least partly EURUSD-specific unless future USDJPY/AUDUSD runs confirm portability.

## How to Run

Run sweeps:

```bash
python scripts/run_cross_pair_sweeps.py \
  --output-root outputs/cross_pair_sweeps
```

Run aggregation:

```bash
python scripts/analyze_cross_pair_robustness.py \
  --input-root outputs/cross_pair_sweeps \
  --output-dir outputs/cross_pair_robustness
```

## Interpretation Notes

- Strong configs should rank well across multiple pairs, not just one symbol.
- Forward ranges are shorter; forward PF is used as survival screening, not strict validation.
- Treat low-sample forward buckets carefully.
