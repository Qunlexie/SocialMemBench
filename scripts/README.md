# scripts/ inventory

Grouped by role. If you land here cold, start with `repro/` and the top-level
`Makefile` at the repo root.

## Reproduction (offline, no API keys)

These regenerate paper artifacts from tracked jsonl results. Safe to re-run.

| Script | Reads | Writes | Produces (paper) |
|---|---|---|---|
| `print_paper_numbers.py` | `data/results/<cond>/*.jsonl` | stdout | Table 2, per-tier, per-category, pairwise tests |
| `recompute_bootstrap.py` | `data/results/<cond>/*.jsonl` | `data/results/bootstrap_cis.json` | 95% CIs on Mean^N |
| `build_ablation_tables.py` | `data/results/ablation/<cond>/ans=<A>__k=<K>/*.jsonl` | `data/results/tables/{answerer_sweep,topk_sweep,extractor_swap}.csv` | Tables 13, 14, 15 |
| `build_category_counts.py` | `data/qa/*.jsonl` | `data/results/category_counts.csv` | per-category QA counts |
| `sensitivity_qc_threshold.py` | `data/qa/*_qc.json` | `data/verify/sensitivity_qc_threshold.json` | QC threshold sensitivity |
| `build_sensitivity_table.py` | `data/verify/sensitivity_qc_threshold.json` | `data/verify/sensitivity_threshold_table.{csv,tex}` | appendix sensitivity table |
| `finalize_paper_numbers.py` | all of the above | orchestrator; runs `pdflatex` at end | end-to-end paper refresh |

Wrappers around these live in `scripts/repro/`.

## Cleanup utilities (offline)

| Script | Purpose |
|---|---|
| `cleanup/list_icloud_duplicates.py` | Enumerate `<name> 2/` shadow dirs iCloud produced; dry-run only. |
| `cleanup/purge_adapter_caches.py` | List (and optionally `--purge`) gitignored adapter caches under `data/.*`. Frees up to 2.6 GB. |

## Evaluation (requires API keys, costs money)

| Script | Purpose |
|---|---|
| `run_evals.sh` | Idempotent driver over all networks x conditions. Uses smb310/smb311 conda envs. Skips already-scored pairs. |
| `run_ablation.py` | Score one (network, condition, answerer, top_k) cell into `data/results/ablation/`. Refuses to re-ingest; requires the main-run ingestion sentinel. |
| `run_ablation_grid.sh` | Drive `run_ablation.py` over a full sweep. |
| `dedup_results.py` | Deduplicate re-appended eval rows to canonical last-write-wins. |

## HuggingFace dataset build (needs `HF_TOKEN` for push)

| Script | Purpose |
|---|---|
| `build_hf_dataset.py` | Emit 4-table parquet under `hf_dataset/`. |
| `build_croissant.py` | Emit Croissant 1.0 + Responsible AI metadata. |
| `validate_hf_dataset.py` | FK consistency, schema invariants, JSON validity, semantic-empty allowlist. Run after every parquet emit. |
| `validate_croissant.py` | Croissant JSON-LD conformance. |
| `push_hf_dataset.py` | Upload to HF Hub. Needs `HF_TOKEN`. |
| `build_hf_dataset_README.md.j2` | Jinja2 template for dataset card. |

## Data fixers (rarely needed; drift patches)

Apply these only when the corresponding drift is detected. See CLAUDE.md
"Data Fix Philosophy" for the fix-hierarchy that governs when each is
appropriate.

| Script | Purpose |
|---|---|
| `fix_pci_verbatim.py` | Restore `planted_challenge_index[].evidence_span` to verbatim corpus content. |
| `fix_qa_anchor_verbatim.py` | Restore `qa.evidence_anchors[].message_excerpt` to verbatim. |
| `backfill_active_participants.py` | Derive `session.active_participants` from speakers. |
| `backfill_session_topics.py` | Per-network curated session topics for older networks. |
| `scrub_em_dashes.py` | Bulk-replace em dashes in generated text. |
| `rewrite_questions.py` / `llm_residual_rewrite.py` | LLM-based question rewriting (needs API keys). |

## Internal scratch (gitignored)

Filenames starting with `_` are personal working copies and are excluded from
git by `scripts/_*.py` / `scripts/_*.sh` patterns. Do not rely on them for
reproduction.
