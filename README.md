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

Run backtest:

```bash
python scripts/run_backtest.py \
  --input tests/fixtures/sample_bars_15m.parquet \
  --strategy session_breakout \
  --output-dir outputs
```

Outputs:

- `outputs/trades.parquet`
- `outputs/metrics.json`

## Data Ingestion (Dukascopy EURUSD Ticks)

The project includes scripts to download Dukascopy hourly tick files (`.bi5`), clean ticks, build 15m bars, and add session labels.

### 1. Download raw tick data

This downloads hourly EURUSD tick files for a year (default: 2023):

```bash
.venv/bin/python scripts/download_dukascopy_ticks.py \
  --year 2023 \
  --output-dir data/raw/dukascopy/EURUSD \
  --max-workers 16 \
  --timeout-seconds 60 \
  --retries 2
```

Raw files are stored under:

- `data/raw/dukascopy/EURUSD/<year>/<month>/<day>/<hour>h_ticks.bi5`

### 2. Clean raw ticks

This step:
- parses timestamps in UTC
- removes duplicate ticks
- computes `mid` and `spread`
- writes a parquet tick dataset

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

### 4. Add sessions + validate

Adds `session_label` (`asia`, `london`, `new_york`), checks continuity, and reports spread statistics.

```bash
.venv/bin/python scripts/add_sessions.py \
  --input-file data/bars/15m/eurusd_bars_15m_2023_raw.parquet \
  --output-file data/bars/15m/eurusd_bars_15m_2023.parquet \
  --report-file data/bars/15m/eurusd_bars_15m_2023_report.json
```

Final dataset:

- `data/bars/15m/eurusd_bars_15m_2023.parquet`

### 5. Run backtest on generated data

```bash
.venv/bin/python scripts/run_backtest.py \
  --input data/bars/15m/eurusd_bars_15m_2023.parquet \
  --strategy session_breakout \
  --output-dir outputs/dukascopy_2023
```
