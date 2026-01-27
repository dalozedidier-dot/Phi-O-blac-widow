#!/usr/bin/env bash
# run_collector_tests.sh
#
# Wrapper unique pour exécuter les tests collector.
# Appelle tests/test_llm_collector_exhaustive.sh (et rien d'autre).
# Anti-récursion : si déjà dans l'exhaustif, on refuse de relancer.

set -Eeuo pipefail

if [[ "${TRACE:-0}" == "1" ]]; then
  set -x
fi

trap 'rc=$?;
  echo "❌ ERR rc=$rc file=${BASH_SOURCE[0]} line=$LINENO cmd=${BASH_COMMAND}" >&2;
  exit "$rc"
' ERR

# Repo root
if command -v git >/dev/null 2>&1 && git rev-parse --show-toplevel >/dev/null 2>&1; then
  cd "$(git rev-parse --show-toplevel)"
else
  cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# Anti-récursion : marqueur d'entrée
if [[ "${IN_COLLECTOR_EXHAUSTIVE:-0}" == "1" ]]; then
  echo "❌ recursion_guard: already in collector exhaustive context" >&2
  exit 2
fi
export IN_COLLECTOR_EXHAUSTIVE=1

# Timeout global optionnel (en secondes). Exemple: COLLECTOR_TIMEOUT=900
if [[ -n "${COLLECTOR_TIMEOUT:-}" ]]; then
  exec timeout "${COLLECTOR_TIMEOUT}" bash tests/test_llm_collector_exhaustive.sh
else
  exec bash tests/test_llm_collector_exhaustive.sh
fi
