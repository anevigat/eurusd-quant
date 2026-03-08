# eurusd_quant

Minimal MVP for backtesting a EURUSD M15 Session Range Breakout strategy with a realistic bar-based execution simulator.

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

```bash
.venv/bin/python scripts/download_dukascopy_ticks.py \
  --year 2023 \
  --output-dir data/raw/dukascopy/EURUSD \
  --max-workers 16 \
  --timeout-seconds 60 \
  --retries 2
```

Raw files are saved under:

- `data/raw/dukascopy/EURUSD/<year>/<month>/<day>/<hour>h_ticks.bi5`

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

## Running backtests

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

Backtest outputs:

- `trades.parquet`
- `metrics.json`

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

## Example commands

```bash
# Full pipeline + backtest + diagnostics
.venv/bin/python scripts/download_dukascopy_ticks.py --year 2023 --output-dir data/raw/dukascopy/EURUSD --max-workers 16 --timeout-seconds 60 --retries 2
.venv/bin/python scripts/clean_ticks.py --input-dir data/raw/dukascopy/EURUSD/2023 --output-file data/ticks/clean/eurusd_ticks_2023.parquet
.venv/bin/python scripts/build_bars.py --input-file data/ticks/clean/eurusd_ticks_2023.parquet --output-file data/bars/15m/eurusd_bars_15m_2023_raw.parquet
.venv/bin/python scripts/add_sessions.py --input-file data/bars/15m/eurusd_bars_15m_2023_raw.parquet --output-file data/bars/15m/eurusd_bars_15m_2023.parquet --report-file data/bars/15m/eurusd_bars_15m_2023_report.json
.venv/bin/python scripts/run_backtest.py --input data/bars/15m/eurusd_bars_15m_2023.parquet --strategy session_breakout --output-dir outputs/dukascopy_2023
.venv/bin/python scripts/analyze_backtest.py --trades outputs/dukascopy_2023/trades.parquet --metrics outputs/dukascopy_2023/metrics.json --bars data/bars/15m/eurusd_bars_15m_2023.parquet --strategy session_breakout --output-dir outputs/diagnostics
```
