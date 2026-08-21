# SocialMemBench reproduction entrypoint.
#
# All targets below are OFFLINE. They read tracked artifacts under data/ and
# regenerate paper tables + figures without touching any external API.
#
# Targets that require API keys (running new evaluations, building/pushing the
# HF dataset) are documented at the bottom and are NOT part of `make all`.
#
# Quick tour:
#   make setup          Install the package in editable mode
#   make paper          One-shot: tables + figures + printed numbers
#   make tables         Regenerate every CSV table from tracked jsonl results
#   make figures        Regenerate every figure PDF/PNG
#   make paper-numbers  Print the numbers cited in the paper
#   make verify         Regenerate outputs, diff against tracked copies
#   make clean-icloud   List iCloud "graphiti 2/" duplicate directories (dry-run)
#   make clean-caches   List adapter caches under data/.* (dry-run)
#   make help           Print this menu

PY := python3
ROOT := $(shell pwd)

.DEFAULT_GOAL := help

.PHONY: help setup paper tables figures paper-numbers verify \
        clean-icloud clean-caches evals hf-build hf-push

help:
	@awk '/^# / { sub(/^# /, "", $$0); print }' $(MAKEFILE_LIST) | sed -n '1,20p'

setup:
	pip install -e .

# ---------------------------------------------------------------------------
# Offline reproduction (no API keys)
# ---------------------------------------------------------------------------

paper: tables figures paper-numbers

tables:
	@echo ">>> Bootstrap CIs"
	$(PY) scripts/recompute_bootstrap.py
	@echo ">>> Ablation tables (13/14/15)"
	$(PY) scripts/build_ablation_tables.py
	@echo ">>> Category counts (Table 6)"
	$(PY) scripts/build_category_counts.py
	@echo ">>> QC-threshold sensitivity (appendix)"
	$(PY) scripts/sensitivity_qc_threshold.py || true
	$(PY) scripts/build_sensitivity_table.py

figures:
	$(PY) figures/generate_figures.py

paper-numbers:
	$(PY) scripts/print_paper_numbers.py

verify:
	bash scripts/repro/verify_reproduction.sh

clean-icloud:
	$(PY) scripts/cleanup/list_icloud_duplicates.py

clean-caches:
	$(PY) scripts/cleanup/purge_adapter_caches.py --dry-run

# ---------------------------------------------------------------------------
# Online targets (require API keys; NOT part of `make all` or `make paper`)
# ---------------------------------------------------------------------------

# Rerun evaluations. Uses smb310/smb311 conda envs. Idempotent: skips already-
# scored pairs. See scripts/run_evals.sh for env-var overrides.
evals:
	bash scripts/run_evals.sh

# Build the HuggingFace dataset artifacts under hf_dataset/.
hf-build:
	$(PY) scripts/build_hf_dataset.py
	$(PY) scripts/build_croissant.py
	$(PY) scripts/validate_hf_dataset.py
	$(PY) scripts/validate_croissant.py

# Push the built HF dataset. Requires HF_TOKEN in env.
hf-push:
	$(PY) scripts/push_hf_dataset.py
