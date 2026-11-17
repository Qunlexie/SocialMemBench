#!/usr/bin/env bash
# Print every headline number cited in the paper.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PY="${PY:-python3}"

"$PY" scripts/print_paper_numbers.py

echo
echo "== Human-judge agreement (Appendix C.4)"
"$PY" scripts/human_judge_agreement.py analyze
