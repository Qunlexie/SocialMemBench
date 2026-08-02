#!/bin/bash
# Ablation grid orchestrator.
#
# Sweeps: 8 conditions x N networks x SWEEP_CELLS.
# Uses scripts/run_ablation.py underneath; that script guarantees baseline
# data/results/{cond}/{net}.jsonl is never touched.
#
# Usage:
#   ./scripts/run_ablation_grid.sh               # small-tier default
#   NETWORKS="grp_9c0d1e2f grp_8b9c0d1e" ./scripts/run_ablation_grid.sh
#   CONDITIONS="naive_rag graphiti" ./scripts/run_ablation_grid.sh
#   SWEEP="ans=gpt-4o:k=10 ans=gpt-4o-mini:k=20" ./scripts/run_ablation_grid.sh
#
# Skip-if-exists is enforced inside run_ablation.py; re-runs are cheap.

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

LOCK="/tmp/smb_ablation_grid.lock"
if [ -e "$LOCK" ]; then
    echo "Another run is in progress (lock at $LOCK). Remove it if that is not the case."
    exit 1
fi
trap 'rm -f "$LOCK"' EXIT INT TERM
touch "$LOCK"

# Small-tier default (extracted from scripts/recompute_bootstrap.py).
DEFAULT_NETWORKS="grp_0d1e2f3a grp_1a2b3c4d grp_2b3c4d5e grp_3c4d5e6f grp_4d5e6f7a \
grp_5e6f7a8b grp_6f7a8b9c grp_7a8b9c0d grp_8b9c0d1e grp_9c0d1e2f \
grp_a9b0c1d2 grp_c1d2e3f4 grp_d4e5f6a7 grp_e6f7a8b9 grp_f7a8b9c0"

# All 8 conditions (must match paper).
DEFAULT_CONDITIONS="llm_mini naive_rag subject_rag smg graphiti langmem mem0_local cognee"

# Sweep cells. Baseline (ans=gpt-4o-mini, k=10) is skipped since it matches
# published numbers already in data/results/{cond}/{net}.jsonl.
# Answerer sweep: gpt-4o and gemini-2.5-flash at k=10.
# Top-k sweep: gpt-4o-mini at k in {3, 5, 20, 50, 10000}.
DEFAULT_SWEEP="\
ans=gpt-4o:k=10 \
ans=gemini-2.5-flash:k=10 \
ans=gpt-4o-mini:k=3 \
ans=gpt-4o-mini:k=5 \
ans=gpt-4o-mini:k=20 \
ans=gpt-4o-mini:k=50 \
ans=gpt-4o-mini:k=10000"

NETWORKS="${NETWORKS:-$DEFAULT_NETWORKS}"
CONDITIONS="${CONDITIONS:-$DEFAULT_CONDITIONS}"
SWEEP="${SWEEP:-$DEFAULT_SWEEP}"

# Count expected cells.
NN=$(echo "$NETWORKS" | wc -w | tr -d ' ')
NC=$(echo "$CONDITIONS" | wc -w | tr -d ' ')
NS=$(echo "$SWEEP" | wc -w | tr -d ' ')
TOTAL=$((NN * NC * NS))
echo "==============================================="
echo "Ablation grid: $NC conditions x $NN networks x $NS sweep cells = $TOTAL runs"
echo "==============================================="

DONE=0
FAILED=0
for cell in $SWEEP; do
    ANS="${cell%%:*}"; ANS="${ANS#ans=}"
    K="${cell##*:}";   K="${K#k=}"
    for cond in $CONDITIONS; do
        for net in $NETWORKS; do
            DONE=$((DONE + 1))
            echo ""
            echo "[$DONE/$TOTAL] cond=$cond net=$net ans=$ANS k=$K"
            if ! python3 scripts/run_ablation.py \
                    --network "$net" --condition "$cond" \
                    --answerer "$ANS" --top-k "$K" 2>&1 | tail -6; then
                echo "  FAILED"
                FAILED=$((FAILED + 1))
            fi
        done
    done
done

echo ""
echo "==============================================="
echo "Grid complete: $DONE runs attempted, $FAILED failed"
echo "==============================================="
