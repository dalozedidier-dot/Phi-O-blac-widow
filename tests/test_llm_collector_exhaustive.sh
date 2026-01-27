#!/usr/bin/env bash
# tests/test_llm_collector_exhaustive.sh
#
# Fix boucle:
# - Ce script ne doit JAMAIS appeler run_collector_tests.sh.
# - Il exécute directement les checks + le collecteur.
# - validate_contract_warnings.sh est lancé via bash (pas besoin de +x).

set -Eeuo pipefail

# Trace si TRACE=1
if [[ "${TRACE:-0}" == "1" ]]; then
  set -x
fi

trap 'rc=$?;
  echo "❌ ERR rc=$rc file=${BASH_SOURCE[0]} line=$LINENO cmd=${BASH_COMMAND}" >&2;
  exit "$rc"
' ERR

log() { printf '%s\n' "$*" >&2; }

# --- Repo root ---
if command -v git >/dev/null 2>&1 && git rev-parse --show-toplevel >/dev/null 2>&1; then
  cd "$(git rev-parse --show-toplevel)"
else
  cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

# --- Logs ---
ART_DIR="${ART_DIR:-test-reports/collector}"
mkdir -p "$ART_DIR"
LOG_FILE="${LOG_FILE:-$ART_DIR/collector_exhaustive.log}"

exec > >(tee -a "$LOG_FILE") 2>&1

log "collector exhaustive start"
log "***"
log "bash=${BASH_VERSION}"
log "trace=${TRACE:-0}"
log "art_dir=${ART_DIR}"
log "log_file=${LOG_FILE}"
log "pwd=$(pwd)"

# --- Pré-checks ---
command -v python >/dev/null 2>&1 || { log "missing_cmd=python"; exit 1; }
[[ -f "contract_probe.py" ]] || { log "missing_file=contract_probe.py"; exit 1; }

# --- Compile rapide ---
log "py_compile: start"
python -m py_compile contract_probe.py
log "py_compile: done"

# --- Baseline optionnelle ---
if [[ "${GENERATE_BASELINE:-0}" == "1" ]]; then
  log "generate_baseline=1"
  [[ -f "phi_otimes_o_instrument_v0_1.py" ]] || { log "missing_file=phi_otimes_o_instrument_v0_1.py"; exit 1; }
  mkdir -p .contract
  python contract_probe.py \
    --instrument ./phi_otimes_o_instrument_v0_1.py \
    --out .contract/contract_baseline.json
else
  log "generate_baseline=0"
fi

# --- Contract warnings (via bash, pas besoin de chmod +x) ---
if [[ -f "./validate_contract_warnings.sh" ]]; then
  log "validate_contract_warnings: start"
  bash ./validate_contract_warnings.sh
  log "validate_contract_warnings: done"
else
  log "validate_contract_warnings_skipped: missing_file"
fi

# --- Collector LLM (direct) ---
if [[ -f "scripts/phio_llm_collect.sh" ]]; then
  log "collector: scripts/phio_llm_collect.sh"
  bash scripts/phio_llm_collect.sh
else
  log "collector_missing: scripts/phio_llm_collect.sh"
  exit 1
fi

# --- Tests collector pytest (si présents) ---
if [[ -d "tests" ]] && ls tests/test_*collector*.py >/dev/null 2>&1; then
  log "pytest_collector: start"
  mkdir -p test-reports/test-results
  python -m pytest -q \
    tests/test_*collector*.py \
    --junitxml=test-reports/test-results/pytest-collector.xml
  log "pytest_collector: done"
else
  log "pytest_collector: none_detected"
fi

log "collector exhaustive end"
