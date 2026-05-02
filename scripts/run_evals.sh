#!/bin/bash
# Incremental eval runner for medium + large tier networks.
# Safe to interrupt and rerun — CLI skips already-scored pairs.
#
# Usage: bash scripts/run_evals.sh [--dry-run]
#
# Environment variables (all optional; sensible defaults provided):
#   SMB_REPO_ROOT   path to repo root (default: derived from script location)
#   CONDA_BASE      conda install root (default: from `conda info --base`)
#   SMB_PYTHON_311  python for smb311 env  (default: $CONDA_BASE/envs/smb311/bin/python)
#   SMB_PYTHON_310  python for smb310 env  (default: $CONDA_BASE/envs/smb310/bin/python)
#
# Example: CONDA_BASE=/opt/anaconda3 bash scripts/run_evals.sh
# Guard against duplicate instances
LOCKFILE="/tmp/smb_run_evals.lock"
if [ -f "$LOCKFILE" ] && kill -0 "$(cat $LOCKFILE)" 2>/dev/null; then
    echo "ERROR: Another instance is already running (PID $(cat $LOCKFILE)). Exiting."
    exit 1
fi
echo $$ > "$LOCKFILE"
trap "rm -f $LOCKFILE" EXIT

# PROJ: defaults to repo root (one level up from scripts/), override via env if needed
PROJ="${SMB_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PROJ"

DRY_RUN=0
if [[ "$1" == "--dry-run" ]]; then DRY_RUN=1; fi

# Conda is required for adapter envs (smb310, smb311). Override CONDA_BASE
# if your install is elsewhere (default tries common locations).
CONDA_BASE="${CONDA_BASE:-$(conda info --base 2>/dev/null || echo "$HOME/miniconda3")}"
source "$CONDA_BASE/etc/profile.d/conda.sh"

run_eval() {
    local env="$1"
    local network="$2"
    local condition="$3"
    local summary="data/results/${condition}/${network}_summary.json"

    if [[ -f "$summary" ]]; then
        echo "  SKIP $network/$condition (already done)"
        return
    fi

    echo "  RUN  $network/$condition [env=$env]"
    if [[ $DRY_RUN -eq 1 ]]; then return; fi

    # Adapter env Pythons — derived from CONDA_BASE, override via env vars
    if [[ "$env" == "smb311" ]]; then
        PYTHON="${SMB_PYTHON_311:-$CONDA_BASE/envs/smb311/bin/python}"
    else
        PYTHON="${SMB_PYTHON_310:-$CONDA_BASE/envs/smb310/bin/python}"
    fi
    "$PYTHON" -m eval.cli --network "$network" --condition "$condition"
    local exit_code=$?
    if [[ $exit_code -eq 0 ]] && [[ -f "$summary" ]]; then
        echo "  DONE $network/$condition"
    else
        echo "  FAIL $network/$condition (exit=$exit_code, summary_exists=$(test -f "$summary" && echo yes || echo no))"
    fi
}

# Medium tier networks
MEDIUM=(
  grp_a0b1c2d3 grp_a1b2c3d4 grp_a3b4c5d6 grp_a5b6c7d8
  grp_b0c1d2e3 grp_b2c3d4e5 grp_b6c7d8e9
  grp_c2d3e4f5 grp_c3d4e5f6 grp_d2e3f4a5 grp_dba9214c
  grp_e8f9a0b1 grp_f2e3d4c5 grp_f9a0b1c2
)

# Large tier networks
LARGE=(
  grp_b1c2d3e4 grp_e5f6a7b8 grp_f6g7h8i9
)

ALL_NETS=("${MEDIUM[@]}" "${LARGE[@]}")

echo "=== Starting incremental evals ($(date)) ==="
echo "Networks: ${#ALL_NETS[@]} | Dry run: $DRY_RUN"
echo ""

# smb310: all standard conditions including naive_rag
echo "--- smb310 env: llm_mini, naive_rag, mem0_local, smg, subject_rag, graphiti, cognee ---"
for net in "${ALL_NETS[@]}"; do
    for cond in llm_mini naive_rag mem0_local smg subject_rag graphiti cognee; do
        run_eval smb310 "$net" "$cond"
    done
done

# smb311: langmem only
echo "--- smb311 env: langmem ---"
for net in "${ALL_NETS[@]}"; do
    run_eval smb311 "$net" langmem
done

echo ""
echo "=== All evals complete ($(date)) ==="
