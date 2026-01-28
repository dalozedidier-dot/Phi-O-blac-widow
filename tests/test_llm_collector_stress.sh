#!/usr/bin/env bash
# tests/test_llm_collector_stress.sh
# Test de charge : beaucoup de fichiers + structure large.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COLLECTOR="${COLLECTOR:-$REPO_ROOT/scripts/phio_llm_collect.sh}"

echo "💥 TEST DE CHARGE EXTRÊME (fichiers nombreux) 💥"
STRESS_ROOT="$(mktemp -d)"
OUT="$REPO_ROOT/_stress_output"
trap 'rm -rf "$STRESS_ROOT" "$OUT" 2>/dev/null || true' EXIT

echo "Répertoire de test: $STRESS_ROOT"

echo "Création de 1000 fichiers..."
for i in $(seq 1 1000); do
  echo "File $i content" > "$STRESS_ROOT/file_$i.txt"
done

echo "Création de 100 répertoires x 10 fichiers..."
for d in $(seq 1 100); do
  mkdir -p "$STRESS_ROOT/dir_$d"
  for f in $(seq 1 10); do
    echo "Content in dir $d file $f" > "$STRESS_ROOT/dir_$d/file_$f.txt"
  done
done

echo "Lancement du collecteur..."
if command -v timeout >/dev/null 2>&1; then
  timeout 30 env QUIET=1 MAX_FILE_BYTES=100000 MAX_CONCAT_LINES=50000 "$COLLECTOR" "$STRESS_ROOT" "$OUT" >/dev/null 2>&1 || code=$?
else
  env QUIET=1 MAX_FILE_BYTES=100000 MAX_CONCAT_LINES=50000 "$COLLECTOR" "$STRESS_ROOT" "$OUT" >/dev/null 2>&1 || code=$?
fi
code="${code:-0}"

if [ "$code" -eq 124 ]; then
  echo "❌ TIMEOUT"
  exit 1
elif [ "$code" -ne 0 ]; then
  echo "❌ Échec collecteur (code $code)"
  exit 1
fi

for f in tree.txt manifest.json phio_llm_bundle.tar.gz; do
  test -f "$OUT/$f" || { echo "❌ Manquant: $f"; exit 1; }
done

python3 "$REPO_ROOT/scripts/validate_manifest.py" "$OUT/manifest.json" >/dev/null 2>&1 || { echo "❌ Manifest invalide"; exit 1; }

entries=$(python3 - <<'PY' "$OUT/manifest.json"
import json, sys
print(len(json.load(open(sys.argv[1], encoding="utf-8")).get("entries",[])))
PY
)
echo "📊 Entrées manifest: $entries"
echo "✅ OK"
