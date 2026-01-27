#!/usr/bin/env bash
# run_collector_tests.sh
set -Eeuo pipefail

# Active trace globale si TRACE=1
if [[ "${TRACE:-0}" == "1" ]]; then
  set -x
fi

# Se recaler sur repo root
if command -v git >/dev/null 2>&1 && git rev-parse --show-toplevel >/dev/null 2>&1; then
  cd "$(git rev-parse --show-toplevel)"
else
  cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# Exécute l'exhaustif
exec bash tests/test_llm_collector_exhaustive.sh
