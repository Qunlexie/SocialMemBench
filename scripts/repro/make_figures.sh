#!/usr/bin/env bash
# Regenerate every PDF/PNG figure from tracked data.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PY="${PY:-python3}"

echo "Generating figures/ ..."
"$PY" figures/generate_figures.py
echo "Figures regenerated."
