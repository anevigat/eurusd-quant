#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/prepare_pair_data.sh <PAIR> [YYYY-MM-DD]

Examples:
  bash scripts/prepare_pair_data.sh EURUSD
  bash scripts/prepare_pair_data.sh USDJPY 2026-03-11
EOF
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 1
fi

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

PAIR="$(echo "$1" | tr '[:lower:]' '[:upper:]')"
if ! [[ "${PAIR}" =~ ^[A-Z]{6}$ ]]; then
  echo "Error: invalid pair '${1}'. Expected 6 alphabetic characters, e.g. EURUSD." >&2
  exit 1
fi
PAIR_LOWER="$(echo "${PAIR}" | tr '[:upper:]' '[:lower:]')"

if [[ $# -eq 2 ]]; then
  TODAY="$2"
  "${PYTHON_BIN}" - "${TODAY}" <<'PY'
import sys
from datetime import date
try:
    date.fromisoformat(sys.argv[1])
except ValueError:
    raise SystemExit("Error: date override must be YYYY-MM-DD")
PY
else
  TODAY="$("${PYTHON_BIN}" - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).date().isoformat())
PY
)"
fi

if [[ "${TODAY}" < "2025-01-01" ]]; then
  echo "Error: end date '${TODAY}' is before 2025-01-01 for range B." >&2
  exit 1
fi

if [[ "${PAIR}" == *JPY ]]; then
  PRICE_SCALE="1000.0"
else
  PRICE_SCALE="100000.0"
fi
MAX_DOWNLOAD_WORKERS=3

RAW_BASE="data/raw/dukascopy"
CLEAN_BASE="data/cleaned_ticks/${PAIR}"
BARS_BASE="data/bars/15m"
OUTPUTS_BASE="outputs"

mkdir -p "${RAW_BASE}" "${CLEAN_BASE}" "${BARS_BASE}" "${OUTPUTS_BASE}"

declare -a GENERATED_BARS=()
declare -a GENERATED_TICKS=()
declare -a GENERATED_VALIDATION_DIRS=()

run_range() {
  local suffix="$1"
  local start_date="$2"
  local end_date="$3"

  local raw_dir="${RAW_BASE}/${PAIR}_${suffix}"
  local manifest_file="${RAW_BASE}/download_manifest_${PAIR}_${suffix}.jsonl"
  local clean_dir="${CLEAN_BASE}/${suffix}"
  local ticks_file="${clean_dir}/${PAIR_LOWER}_ticks_${suffix}.parquet"
  local bars_raw="${BARS_BASE}/${PAIR_LOWER}_bars_15m_${suffix}_raw.parquet"
  local bars_final="${BARS_BASE}/${PAIR_LOWER}_bars_15m_${suffix}.parquet"
  local bars_report="${BARS_BASE}/${PAIR_LOWER}_bars_15m_${suffix}_report.json"
  local validation_dir="${OUTPUTS_BASE}/data_validation_${PAIR}_${suffix}"

  mkdir -p "${raw_dir}" "${clean_dir}" "${validation_dir}"

  echo "Range ${suffix}: ${start_date} -> ${end_date}"
  echo "  downloading..."
  "${PYTHON_BIN}" -u scripts/download_dukascopy_ticks.py \
    --symbol "${PAIR}" \
    --start-date "${start_date}" \
    --end-date "${end_date}" \
    --output-dir "${raw_dir}" \
    --manifest-file "${manifest_file}" \
    --resume \
    --max-workers "${MAX_DOWNLOAD_WORKERS}" \
    --max-retries 5 \
    --timeout 30 \
    --sleep-seconds 0.25

  echo "  retrying failed downloads..."
  "${PYTHON_BIN}" -u scripts/retry_failed_downloads.py \
    --manifest-file "${manifest_file}" \
    --symbol "${PAIR}" \
    --output-dir "${raw_dir}" \
    --resume \
    --max-workers "${MAX_DOWNLOAD_WORKERS}" \
    --max-retries 6 \
    --timeout 30 \
    --sleep-seconds 0.5

  echo "  cleaning ticks..."
  "${PYTHON_BIN}" -u scripts/clean_ticks.py \
    --input-dir "${raw_dir}" \
    --output-file "${ticks_file}" \
    --price-scale "${PRICE_SCALE}"

  echo "  building bars..."
  "${PYTHON_BIN}" -u scripts/build_bars.py \
    --input-file "${ticks_file}" \
    --output-file "${bars_raw}" \
    --symbol "${PAIR}"

  echo "  adding sessions..."
  "${PYTHON_BIN}" -u scripts/add_sessions.py \
    --input-file "${bars_raw}" \
    --output-file "${bars_final}" \
    --report-file "${bars_report}"

  echo "  validating..."
  "${PYTHON_BIN}" -u scripts/validate_dataset.py \
    --start-date "${start_date}" \
    --end-date "${end_date}" \
    --raw-dir "${raw_dir}" \
    --ticks-file "${ticks_file}" \
    --bars-file "${bars_final}" \
    --output-dir "${validation_dir}"

  GENERATED_BARS+=("${bars_final}")
  GENERATED_TICKS+=("${ticks_file}")
  GENERATED_VALIDATION_DIRS+=("${validation_dir}")
}

echo "Preparing ${PAIR} data"
run_range "2018_2024" "2018-01-01" "2024-12-31"
run_range "2025_now" "2025-01-01" "${TODAY}"

echo "Done."
echo "Generated bars:"
for path in "${GENERATED_BARS[@]}"; do
  echo "- ${path}"
done
echo "Generated cleaned ticks:"
for path in "${GENERATED_TICKS[@]}"; do
  echo "- ${path}"
done
echo "Validation outputs:"
for path in "${GENERATED_VALIDATION_DIRS[@]}"; do
  echo "- ${path}"
done
