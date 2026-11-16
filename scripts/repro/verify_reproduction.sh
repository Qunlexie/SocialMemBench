#!/usr/bin/env bash
# Reproducibility gate.
#
# Regenerates every derived artifact (tables, figures, bootstrap CIs) from the
# tracked jsonl results, then diffs each output against the tracked copy. Exit
# code 0 iff nothing drifted, 1 otherwise.
#
# What this catches:
#   - a data fix that silently shifted a number
#   - a script edit that changed a table format
#   - a rounding or bootstrap seed change
#
# What this does NOT catch:
#   - drift in figures (image bytes are not stable across matplotlib versions;
#     we diff CSV/JSON sources instead)
#
# No API calls. Reads tracked artifacts only. Safe to re-run.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PY="${PY:-python3}"

# Snapshot current tracked outputs to a temp tree, regen, then diff.
TMP="$(mktemp -d)"
trap "rm -rf $TMP" EXIT

SNAPSHOT=(
  "data/results/bootstrap_cis.json"
  "data/results/tables/answerer_sweep.csv"
  "data/results/tables/topk_sweep.csv"
  "data/results/tables/extractor_swap.csv"
  "data/results/category_counts.csv"
  "data/verify/sensitivity_threshold_table.csv"
)

for f in "${SNAPSHOT[@]}"; do
  if [ -f "$f" ]; then
    mkdir -p "$TMP/$(dirname "$f")"
    cp "$f" "$TMP/$f"
  fi
done

bash scripts/repro/make_all_tables.sh

FAIL=0
for f in "${SNAPSHOT[@]}"; do
  if [ -f "$TMP/$f" ]; then
    if ! diff -q "$TMP/$f" "$f" >/dev/null 2>&1; then
      echo "DRIFT: $f"
      diff -u "$TMP/$f" "$f" | head -40
      FAIL=1
    fi
  fi
done

if [ "$FAIL" -eq 0 ]; then
  echo "OK: all regenerated tables match tracked copies."
  exit 0
else
  echo "FAILED: at least one artifact drifted (see above)."
  exit 1
fi
