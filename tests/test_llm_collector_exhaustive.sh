#!/usr/bin/env bash
# tests/test_llm_collector_exhaustive.sh
#
# IMPORTANT: NE PAS appeler run_collector_tests.sh (évite boucle)
# Exécute directement le collecteur + validations

set -Eeuo pipefail

if [[ "${TRACE:-0}" == "1" ]]; then
  set -x
fi

trap 'rc=$?; echo "❌ ERR rc=$rc file=${BASH_SOURCE[0]} line=$LINENO cmd=${BASH_COMMAND}" >&2; exit "$rc"' ERR

log() { printf '[%s] %s\n' "$(date +%T)" "$*" >&2; }

errors=0

# repo root
if command -v git >/dev/null 2>&1 && git rev-parse --show-toplevel >/dev/null 2>&1; then
  cd "$(git rev-parse --show-toplevel)"
else
  cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

# logs
ART_DIR="${ART_DIR:-test-reports/collector}"
mkdir -p "$ART_DIR"
LOG_FILE="${LOG_FILE:-$ART_DIR/collector_exhaustive.log}"
exec > >(tee -a "$LOG_FILE") 2>&1

log "collector exhaustive start"
log "bash=${BASH_VERSION}"
log "trace=${TRACE:-0}"
log "art_dir=${ART_DIR}"
log "log_file=${LOG_FILE}"
log "PWD=$(pwd)"

# prérequis
command -v python3 >/dev/null 2>&1 || { log "ERREUR: python3 manquant"; exit 1; }

# compile rapide
log "py_compile: start"
python3 -m py_compile contract_probe.py phi_otimes_o_instrument_v0_1.py contract_warnings.py diagnostic.py extract_conventions.py || { ((errors++)); log "py_compile failed"; }
log "py_compile: done (errors=$errors)"

# baseline (optionnelle)
if [[ "${GENERATE_BASELINE:-0}" == "1" ]]; then
  log "generate_baseline=1"
  mkdir -p .contract
  python3 contract_probe.py \
    --instrument ./scripts/phi_otimes_o_instrument_v0_1.py \
    --out .contract/contract_baseline.json || { ((errors++)); log "generate_baseline failed"; }
else
  log "generate_baseline=0 (skipped)"
fi

# validation warnings
if [[ -f "./validate_contract_warnings.sh" ]]; then
  log "validate_contract_warnings: start"
  bash ./validate_contract_warnings.sh || { ((errors++)); log "validate_contract_warnings failed (rc !=0)"; }
  log "validate_contract_warnings: done"
else
  log "validate_contract_warnings_skipped: missing_file"
fi

# exécution collecteur principal
if [[ -f "scripts/phio_llm_collect.sh" ]]; then
  log "collector_script: start scripts/phio_llm_collect.sh"
  bash scripts/phio_llm_collect.sh || { ((errors++)); log "phio_llm_collect.sh failed (rc !=0)"; }
  log "collector_script: done"
else
  log "ERREUR: scripts/phio_llm_collect.sh manquant"
  ((errors++))
fi

# pytest si présent
if ls tests/test_*collector*.py >/dev/null 2>&1; then
  log "pytest_collector: start"
  mkdir -p test-reports/test-results
  python3 -m pytest -q tests/test_*collector*.py \
    --junitxml=test-reports/test-results/pytest-collector.xml || { ((errors++)); log "pytest failed"; }
  log "pytest_collector: done"
else
  log "pytest_collector: none_detected"
fi

# check git clean (optionnel, souvent cause de rc=1)
if [[ "${SKIP_GIT_CLEAN_CHECK:-0}" != "1" ]]; then
  log "git_status_check: start"
  if git status --porcelain | grep -q .; then
    log "WARNING: git status non clean après run"
    git status --porcelain
    ((errors++))
  else
    log "git_status_check: clean"
  fi
fi

# bilan final
log "collector exhaustive end | errors=$errors"
if (( errors > 0 )); then
  log "→ ÉCHEC (au moins une étape en erreur)"
  exit 1
else
  log "→ SUCCÈS"
  exit 0
fi
