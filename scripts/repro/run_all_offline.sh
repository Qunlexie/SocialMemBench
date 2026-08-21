#!/usr/bin/env bash
# Full offline reproduction from tracked data.
#
# Regenerates every paper table, figure, and headline number in the correct
# order. Zero API calls, zero network access. Safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

bash scripts/repro/make_all_tables.sh
bash scripts/repro/make_figures.sh
bash scripts/repro/print_paper_numbers.sh
