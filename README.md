# eurusd_quant

Minimal MVP for backtesting EURUSD M15 intraday strategies with a realistic bar-based execution simulator.

## Research findings

- [Asian session breakout strategy notes](docs/strategy_asian_range_breakout.md)
- [False breakout reversal strategy summary](docs/strategy_false_breakout_reversal.md)
- [London pullback continuation strategy summary](docs/strategy_london_pullback_continuation.md)
- [Asian range compression breakout strategy summary](docs/strategy_asian_range_compression_breakout.md)
- [False breakout reversal regime diagnostics](docs/research/fbr_regime_diagnostics.md)
- [False breakout reversal multi-year validation](docs/research/false_breakout_reversal_multiyear_validation.md)

## Requirements

- Python 3.11+
- `pandas`, `numpy`, `pyarrow`, `pyyaml`, `pytest`

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Run tests:

```bash
pytest
```

## Data pipeline

The project includes scripts to download Dukascopy hourly tick files (`.bi5`), clean ticks, build 15m bars, and add session labels.

### 1. Download raw tick data

Recommended safe command for large ranges:

```bash
.venv/bin/python scripts/download_dukascopy_ticks.py \
  --symbol EURUSD \
  --start-date 2023-01-01 \
  --end-date 2023-12-31 \
  --output-dir data/raw/dukascopy/EURUSD \
  --resume \
  --max-workers 1 \
  --max-retries 5 \
  --timeout 30 \
  --sleep-seconds 0.25 \
  --max-consecutive-failures 25
```

Raw files are saved under:

- `data/raw/dukascopy/EURUSD/<year>/<month>/<day>/<hour>h_ticks.bi5`
- Manifest is written as `data/raw/dukascopy/download_manifest_YYYY.jsonl`
- Market-closed empty hours are classified as `skipped_no_data` and are not retried

Resume an interrupted run:

```bash
.venv/bin/python scripts/download_dukascopy_ticks.py \
  --symbol EURUSD \
  --start-date 2023-01-01 \
  --end-date 2023-12-31 \
  --output-dir data/raw/dukascopy/EURUSD \
  --resume
```

Retry only failed files from a previous run:

```bash
.venv/bin/python scripts/retry_failed_downloads.py \
  --manifest-file data/raw/dukascopy/download_manifest_2023.jsonl \
  --symbol EURUSD \
  --output-dir data/raw/dukascopy/EURUSD \
  --resume \
  --max-retries 6 \
  --timeout 30 \
  --sleep-seconds 0.5
```

### 2. Clean raw ticks

This step parses UTC timestamps, removes duplicate ticks, and computes `mid` and `spread`.

```bash
.venv/bin/python scripts/clean_ticks.py \
  --input-dir data/raw/dukascopy/EURUSD/2023 \
  --output-file data/ticks/clean/eurusd_ticks_2023.parquet
```

### 3. Build M15 bars

```bash
.venv/bin/python scripts/build_bars.py \
  --input-file data/ticks/clean/eurusd_ticks_2023.parquet \
  --output-file data/bars/15m/eurusd_bars_15m_2023_raw.parquet
```

### 4. Add sessions and validate

```bash
.venv/bin/python scripts/add_sessions.py \
  --input-file data/bars/15m/eurusd_bars_15m_2023_raw.parquet \
  --output-file data/bars/15m/eurusd_bars_15m_2023.parquet \
  --report-file data/bars/15m/eurusd_bars_15m_2023_report.json
```

Final dataset:

- `data/bars/15m/eurusd_bars_15m_2023.parquet`

## Dataset validation

Validate cleaned ticks + bars for a target year:

```bash
.venv/bin/python scripts/validate_dataset.py \
  --year 2022 \
  --raw-dir data/raw/dukascopy/EURUSD/2022 \
  --ticks-file data/cleaned_ticks/EURUSD/2022/eurusd_ticks_2022.parquet \
  --bars-file data/bars/15m/eurusd_bars_15m_2022.parquet \
  --output-dir outputs/data_validation_2022
```

Validate a multi-year range:

```bash
.venv/bin/python scripts/validate_dataset.py \
  --start-date 2018-01-01 \
  --end-date 2024-12-31 \
  --raw-dir data/raw/dukascopy/EURUSD \
  --ticks-file data/cleaned_ticks/EURUSD/2018_2024/eurusd_ticks_2018_2024.parquet \
  --bars-file data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --output-dir outputs/data_validation_2018_2024
```

Continuity diagnostics include both:

- `total_gap_count`: all gaps greater than bar timeframe
- `unexpected_gap_count`: gaps excluding expected weekend market closures

Weekend FX closures are expected and should not be treated as data anomalies.

Validation outputs:

- `outputs/data_validation_2022/bar_continuity.json`
- `outputs/data_validation_2022/spread_stats.json`
- `outputs/data_validation_2022/daily_bar_counts.csv`
- `outputs/data_validation_2022/summary.json`

## Running backtests

Available strategies:

- `session_breakout`
- `asian_range_compression_breakout` (MVP research hypothesis; not a validated edge)
- `false_breakout_reversal` (MVP research hypothesis; not a validated edge)
- `london_pullback_continuation` (MVP research hypothesis; not a validated edge)

Run on fixture data:

```bash
.venv/bin/python scripts/run_backtest.py \
  --input tests/fixtures/sample_bars_15m.parquet \
  --strategy session_breakout \
  --output-dir outputs
```

Run on Dukascopy-derived bars:

```bash
.venv/bin/python scripts/run_backtest.py \
  --input data/bars/15m/eurusd_bars_15m_2023.parquet \
  --strategy session_breakout \
  --output-dir outputs/dukascopy_2023
```

Run false-breakout reversal MVP on Dukascopy-derived bars:

```bash
.venv/bin/python scripts/run_backtest.py \
  --input data/bars/15m/eurusd_bars_15m_2023.parquet \
  --strategy false_breakout_reversal \
  --output-dir outputs/false_breakout_reversal_smoke
```

Run London pullback continuation MVP:

Hypothesis: when overnight drift is strong, the first London pullback to EMA20 may continue in drift direction.

```bash
.venv/bin/python scripts/run_backtest.py \
  --input data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --strategy london_pullback_continuation \
  --output-dir outputs/london_pullback_continuation_smoke
```

Run Asian range compression breakout MVP:

Hypothesis: a compressed Asian range (relative to ATR) can precede London-session breakout expansion.

```bash
.venv/bin/python scripts/run_backtest.py \
  --input data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --strategy asian_range_compression_breakout \
  --output-dir outputs/asian_range_compression_breakout_smoke
```

Backtest outputs:

- `trades.parquet`
- `metrics.json`

Run Asian compression breakout threshold experiments:

```bash
.venv/bin/python scripts/run_asian_compression_experiments.py \
  --input data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --output-root outputs/asian_compression_breakout_experiments \
  --thresholds 4.0 4.5 4.7
```

This writes per-threshold runs under `outputs/asian_compression_breakout_experiments/<threshold>/`
and a combined comparison file at `outputs/asian_compression_breakout_experiments/summary.json`.

## Running diagnostics

```bash
.venv/bin/python scripts/analyze_backtest.py \
  --trades outputs/dukascopy_2023_partial/trades.parquet \
  --metrics outputs/dukascopy_2023_partial/metrics.json \
  --bars data/bars/15m/eurusd_bars_15m_2023.parquet \
  --strategy session_breakout \
  --output-dir outputs/diagnostics \
  --stress-spread-penalty-pips 0.2
```

Diagnostics outputs:

- `outputs/diagnostics/summary.json`
- `outputs/diagnostics/monthly_pnl.csv`
- `outputs/diagnostics/hourly_stats.csv`
- `outputs/diagnostics/stress_test_metrics.json`

## Strategy diagnostics

Analyze trade behavior for any strategy from `trades.parquet` + bars:

```bash
.venv/bin/python scripts/analyze_strategy_behavior.py \
  --trades outputs/false_breakout_reversal_smoke/trades.parquet \
  --bars data/bars/15m/eurusd_bars_15m_2023.parquet \
  --output-dir outputs/false_breakout_reversal_diagnostics
```

This writes:

- `trade_distribution.json`
- `exit_reason_counts.json`
- `win_loss_stats.json`
- `side_stats.json`
- `hourly_stats.csv`
- `excursions.json`
- `holding_time.json`

Run false-breakout side/window segmentation experiments:

```bash
.venv/bin/python scripts/run_false_breakout_segmentation.py \
  --input data/bars/15m/eurusd_bars_15m_2023.parquet \
  --output-root outputs/false_breakout_reversal_segmentation
```

This writes per-combination run folders and:

- `outputs/false_breakout_reversal_segmentation/summary.json`

Run regime diagnostics on frozen multi-year validation outputs:

```bash
.venv/bin/python scripts/analyze_fbr_regimes.py \
  --start-year 2018 \
  --end-year 2024 \
  --trades-root outputs/experiments/false_breakout_reversal_atr_target_0809 \
  --bars-dir data/bars/15m \
  --output-dir outputs/diagnostics/fbr_regime_analysis
```

This writes:

- `outputs/diagnostics/fbr_regime_analysis/regime_summary_by_feature.csv`
- `outputs/diagnostics/fbr_regime_analysis/regime_summary_by_quantile.csv`
- `outputs/diagnostics/fbr_regime_analysis/monthly_performance.csv`
- `outputs/diagnostics/fbr_regime_analysis/yearly_performance.csv`

### Strategy regime experiments: pre-London drift

Run frozen `false_breakout_reversal` by drift regimes where:

- `pre_london_drift = mid_close(07:45) - mid_close(00:00)`
- `drift_down`: drift `< -0.0002`
- `drift_flat`: `-0.0002 <= drift <= 0.0002`
- `drift_up`: drift `> 0.0002`

```bash
.venv/bin/python scripts/run_false_breakout_pre_london_drift.py \
  --bars-file data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --output-dir outputs/false_breakout_pre_london_drift
```

This writes:

- `outputs/false_breakout_pre_london_drift/summary.json`
- `outputs/false_breakout_pre_london_drift/regime_yearly.csv`

Run drift-down side filter comparison (frozen config, `both` vs `short_only`):

```bash
.venv/bin/python scripts/run_false_breakout_drift_down_short_only.py \
  --bars-file data/bars/15m/eurusd_bars_15m_2018_2024.parquet \
  --output-dir outputs/false_breakout_drift_down_short_only
```

This writes:

- `outputs/false_breakout_drift_down_short_only/summary.json`
- `outputs/false_breakout_drift_down_short_only/yearly_breakdown.csv`

Run false-breakout exit-model experiments (fixed to `allowed_side=both`, `08:00-09:00 UTC`):

```bash
.venv/bin/python scripts/run_false_breakout_exit_models.py \
  --input data/bars/15m/eurusd_bars_15m_2023.parquet \
  --output-root outputs/false_breakout_exit_models
```

This writes per-model run folders and:

- `outputs/false_breakout_exit_models/summary.json`

Run frozen multi-year validation (2018-2024) for `false_breakout_reversal` with
`allowed_side=both`, `entry 08:00-09:00 UTC`, `exit_model=atr_target`:

```bash
.venv/bin/python scripts/run_false_breakout_multiyear_validation.py \
  --start-year 2018 \
  --end-year 2024 \
  --bars-dir data/bars/15m \
  --output-root outputs/experiments/false_breakout_reversal_atr_target_0809
```

This writes per-year outputs plus:

- `outputs/experiments/false_breakout_reversal_atr_target_0809/summary.csv`
- `outputs/experiments/false_breakout_reversal_atr_target_0809/monthly_pnl.csv`

## Research diagnostics: Asian range compression

Analyze whether narrower Asian ranges (00:00-06:00 UTC) are followed by larger London moves (07:00-12:00 UTC):

```bash
.venv/bin/python scripts/analyze_range_compression.py \
  --bars data/bars/15m/eurusd_bars_15m_2023.parquet \
  --output-dir outputs/range_compression
```

Outputs:

- `outputs/range_compression/range_stats.csv`
- `outputs/range_compression/summary.json`
- `outputs/range_compression/daily_ranges.csv`

## Running excursion analysis

Compute MFE/MAE distributions and summary ratio from bars + trades:

```bash
.venv/bin/python scripts/analyze_excursions.py \
  --bars data/bars/15m/eurusd_bars_15m_2023.parquet \
  --trades outputs/dukascopy_2023_partial/trades.parquet \
  --output-dir outputs/excursions
```

Excursion outputs:

- `outputs/excursions/mfe_distribution.csv`
- `outputs/excursions/mae_distribution.csv`
- `outputs/excursions/summary.json`

## Running window experiments

Run segmented entry-window experiments for 07-08, 08-09, 09-10 UTC:

```bash
.venv/bin/python scripts/run_window_experiments.py \
  --bars data/bars/15m/eurusd_bars_15m_2023.parquet \
  --strategy session_breakout \
  --entry-window-mode fixed_utc \
  --output-root outputs/window_experiments \
  --run-stress \
  --stress-spread-penalty-pips 0.2
```

London-local interpretation of the same windows:

```bash
.venv/bin/python scripts/run_window_experiments.py \
  --bars data/bars/15m/eurusd_bars_15m_2023.parquet \
  --strategy session_breakout \
  --entry-window-mode london_local \
  --output-root outputs/window_experiments_london_local \
  --run-stress \
  --stress-spread-penalty-pips 0.2
```

Key output:

- `outputs/window_experiments/window_comparison.json`

## Running buffer experiments

Run breakout-buffer experiments for the 07:00-08:00 UTC entry window:

```bash
.venv/bin/python scripts/run_buffer_experiments.py \
  --bars data/bars/15m/eurusd_bars_15m_2023.parquet \
  --strategy session_breakout \
  --output-root outputs/buffer_experiments \
  --run-stress \
  --stress-spread-penalty-pips 0.2
```

Buffer outputs:

- `outputs/buffer_experiments/0_0/`
- `outputs/buffer_experiments/0_1/`
- `outputs/buffer_experiments/0_2/`
- `outputs/buffer_experiments/0_3/`
- `outputs/buffer_experiments/buffer_comparison.json`

## Example commands

```bash
# Full pipeline + backtest + diagnostics
.venv/bin/python scripts/download_dukascopy_ticks.py --symbol EURUSD --start-date 2023-01-01 --end-date 2023-12-31 --output-dir data/raw/dukascopy/EURUSD --resume --max-workers 1 --max-retries 5 --timeout 30 --sleep-seconds 0.25 --max-consecutive-failures 25
.venv/bin/python scripts/retry_failed_downloads.py --manifest-file data/raw/dukascopy/download_manifest_2023.jsonl --symbol EURUSD --output-dir data/raw/dukascopy/EURUSD --resume --max-retries 6 --timeout 30 --sleep-seconds 0.5
.venv/bin/python scripts/clean_ticks.py --input-dir data/raw/dukascopy/EURUSD/2023 --output-file data/ticks/clean/eurusd_ticks_2023.parquet
.venv/bin/python scripts/build_bars.py --input-file data/ticks/clean/eurusd_ticks_2023.parquet --output-file data/bars/15m/eurusd_bars_15m_2023_raw.parquet
.venv/bin/python scripts/add_sessions.py --input-file data/bars/15m/eurusd_bars_15m_2023_raw.parquet --output-file data/bars/15m/eurusd_bars_15m_2023.parquet --report-file data/bars/15m/eurusd_bars_15m_2023_report.json
.venv/bin/python scripts/run_backtest.py --input data/bars/15m/eurusd_bars_15m_2023.parquet --strategy session_breakout --output-dir outputs/dukascopy_2023
.venv/bin/python scripts/analyze_backtest.py --trades outputs/dukascopy_2023/trades.parquet --metrics outputs/dukascopy_2023/metrics.json --bars data/bars/15m/eurusd_bars_15m_2023.parquet --strategy session_breakout --output-dir outputs/diagnostics
.venv/bin/python scripts/analyze_range_compression.py --bars data/bars/15m/eurusd_bars_15m_2023.parquet --output-dir outputs/range_compression
.venv/bin/python scripts/analyze_excursions.py --bars data/bars/15m/eurusd_bars_15m_2023.parquet --trades outputs/dukascopy_2023_partial/trades.parquet --output-dir outputs/excursions
.venv/bin/python scripts/run_buffer_experiments.py --bars data/bars/15m/eurusd_bars_15m_2023.parquet --strategy session_breakout --output-root outputs/buffer_experiments --run-stress --stress-spread-penalty-pips 0.2
.venv/bin/python scripts/run_window_experiments.py --bars data/bars/15m/eurusd_bars_15m_2023.parquet --strategy session_breakout --entry-window-mode fixed_utc --output-root outputs/window_experiments --run-stress --stress-spread-penalty-pips 0.2
```
