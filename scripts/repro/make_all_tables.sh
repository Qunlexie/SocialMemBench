#!/usr/bin/env bash
# Regenerate every CSV/TeX table cited in the paper from tracked data.
# Offline; no API calls; safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PY="${PY:-python3}"

echo "[1/4] Bootstrap CIs -> data/results/bootstrap_cis.json"
"$PY" scripts/recompute_bootstrap.py

echo "[2/4] Ablation tables -> data/results/tables/{answerer_sweep,topk_sweep,extractor_swap}.csv"
"$PY" scripts/build_ablation_tables.py

echo "[3/4] Category counts -> data/results/category_counts.csv"
"$PY" scripts/build_category_counts.py

echo "[4/4] QC-threshold sensitivity -> data/verify/sensitivity_threshold_table.{csv,tex}"
if [ -f data/verify/sensitivity_qc_threshold.json ]; then
  "$PY" scripts/build_sensitivity_table.py
else
  echo "  (skipping) data/verify/sensitivity_qc_threshold.json not present"
  echo "  regenerate it with: python3 scripts/sensitivity_qc_threshold.py"
fi

echo "All tables regenerated."
