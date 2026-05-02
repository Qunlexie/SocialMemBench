# SocialMemBench

**A benchmark for evaluating AI memory architectures in multi-party social group conversations.**

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)
[![Dataset: 1031 QA × 43 networks](https://img.shields.io/badge/QA-1%2C031%20across%2043%20networks-blue)](#dataset-at-a-glance)
[![Quality: 0.952 blind-critic](https://img.shields.io/badge/blind--critic%20mean-0.952-green)](#data-quality)

---

## The problem

Every AI embedded in a group chat uses single-stream memory that conflates speakers. When Sarah says "Mike hates steep trails," the system must attribute this to **Mike** — not Sarah, not the group. No deployed memory architecture does this reliably across 3+ co-present speakers.

Existing memory benchmarks evaluate either (a) language model reasoning given context (LongMemEval, RULER) or (b) single-user / dyadic dialogue (LaMP, LoCoMo, MSC). **SocialMemBench is the first benchmark that evaluates external memory systems — the write/index/retrieve substrate between sessions — in social group settings.**

## Headline result

| Reference / system | Score | Notes |
|---|---:|---|
| Full-context ceiling (LLM with full corpus in window) | **0.721** | Upper-bound; not a memory system |
| Uncompressed retrieval baseline | **0.423** | Naive concatenation + retrieve, not a memory system |
| **Best deployed memory system** (Graphiti) | **0.293** | 59% gap vs. ceiling |
| LangMem | 0.241 | |
| Mem0 | 0.198 | |
| Cognee | 0.186 | |

The 0.43-point gap between the full-context ceiling and the best deployed system isn't a model-capacity limit; it's an **architectural failure mode** of single-stream memory designs facing multi-party attribution. The benchmark localizes the failure across nine query types so designers can target the specific architectural weakness.

## Dataset at a glance

- **43 ego networks** spanning 5 social-group types (close friends, family, recreational clubs, interest communities, acquaintance networks)
- **1,031 question–answer pairs** across **9 query types** (Q1–Q9)
- **3 size tiers**: small (4–6 members), medium (8–14), large (15–30)
- **7,355 conversation turns** across **348 sessions**
- **430 personas** with structured profiles (Big Five, communication style, preferences, speaking quirks)
- **Quality**: corpus-wide blind-critic mean **0.952**, pass-rate **99.9 %** (≥0.70). Every QA pair is checked by a blind critic that has never seen the planted-challenge metadata. Validator runs over the parquet release: 0 schema violations, 0 non-verbatim evidence anchors, 0 em-dashes in unprotected message text.

## Query types

| ID | Name | What it tests |
|----|------|--------------|
| Q1 | Single-contact recall | One person's implicit preference from conversation history |
| Q2 | Group decision recall | Group decision + whether any individual dissented |
| Q3 | Multi-contact aggregation | All members' preferences on a single domain |
| Q4 | Contamination probe | Correct attribution when two speakers are easily confused |
| Q5 | Theory-of-mind reference | Tracking what person A revealed about person B's preference |
| Q6 | Norm vs. individual | Whether a stated group norm actually applies to everyone |
| Q7 | Relational edge query | Relationship history between two members revealed in chat |
| Q8 | Temporal preference evolution | How a person's preference changed across sessions |
| Q9 | Departed-member recall | Last known preference of a member who left the group |

## Quick start

Load the dataset from HuggingFace:

```python
from datasets import load_dataset

networks      = load_dataset("SocialMemBench", "networks",      split="data")
personas      = load_dataset("SocialMemBench", "personas",      split="data")
conversations = load_dataset("SocialMemBench", "conversations", split="data")
qa            = load_dataset("SocialMemBench", "qa",            split="data")

# All four configs share `network_id` as the join key
print(qa[0]["question"], "→", qa[0]["answer"])
```

Run an evaluation locally:

```bash
pip install -e .
python -m eval.cli --condition graphiti --network grp_a0b1c2d3
```

Adapter caches (graphiti / cognee / chroma) regenerate from `data/conversations/` on first run; expect ~$150–500 in embedding + extraction calls for a full corpus rebuild. Final per-pair scores are checked into `data/results/`, so you can do analysis without re-running.

## Data shape

Four logical tables joinable on `network_id`:

| Table | Rows | Description |
|-------|------|-------------|
| `networks` | 43 | One row per ego network — group type, size, tier, edges, group norms |
| `personas` | 430 | One row per persona — Big Five, communication profile, preferences, speaking quirks |
| `conversations` | 7,355 | One row per turn — speaker, message, timestamp, session metadata |
| `qa` | 1,031 | One row per question — query type, answer, evidence anchors, blind-critic score |

Source files on disk are JSON / JSONL under `data/`. The HuggingFace release ships parquet with [Croissant](https://docs.mlcommons.org/croissant/) metadata including the Responsible AI fields NeurIPS requires.

## Methodology

### Generation
Synthetic group conversations are generated with **planted memory challenges** — implicit preferences, group decisions, theory-of-mind references, temporal shifts — embedded at known `(speaker, session, turn)` coordinates. The QA pairs are generated against those planted challenges; the planted-challenge index is stripped from the public release so reviewers and downstream researchers test against the QA pairs, not against leaked ground-truth metadata.

Generation specs live in `skills/`. Each stage (network → conversations → QA → verify → QC) is a deterministic, reproducible procedure documented with explicit pass/fail criteria.

### Validation pipeline

| Stage | What it checks |
|-------|----------------|
| `smb-verify` | Structural integrity — schemas, evidence-span verbatim, ISO timestamps, persona distinctness |
| `smb-qc` | Blind-critic QA quality — an evaluator that hasn't seen planted-challenge metadata answers each QA from the conversation alone, and the answer is scored against the recorded ground truth |

`scripts/validate_hf_dataset.py` runs comprehensive checks on the parquet output: foreign-key consistency across the four tables, schema invariants, JSON validity in nested fields, value ranges, semantic-empty allowlist (e.g., `options` is correctly empty for non-multiple-choice questions), and em-dash absence in unprotected text. Required to pass before any HuggingFace push.

### Reproducible data fixes

The `scripts/` directory ships fix-and-validate utilities for common data-drift patterns we encountered during scaling:

| Script | Purpose |
|--------|---------|
| `validate_hf_dataset.py` | Pre-upload validator (run after every parquet emit) |
| `build_hf_dataset.py` | Build the 4-table parquet release |
| `build_croissant.py` | Generate Croissant 1.0 + RAI metadata |
| `fix_pci_verbatim.py` | Repair planted-challenge-index spans → verbatim corpus content |
| `fix_qa_anchor_verbatim.py` | Repair QA evidence-anchor excerpts → verbatim |
| `scrub_em_dashes.py` | Replace em-dashes lockstep across messages and any anchors that reference them |
| `backfill_session_topics.py` | Per-network topic backfill |
| `backfill_active_participants.py` | Derive session active-participants from speakers |
| `recompute_bootstrap.py` | Regenerate paper bootstrap CIs |
| `print_paper_numbers.py` | Recompute paper headline numbers from `data/results/` |

## Repository layout

```
.
├── data/
│   ├── manifest.json            # central manifest
│   ├── raw/                     # Stage 1: 43 ego-network JSON files
│   ├── conversations/           # Stage 2: 43 corpora (348 sessions, 7,355 turns)
│   ├── qa/                      # Stage 3: QA pairs + per-network QC reports
│   ├── verify/                  # Structural verification reports (canonical schema 2.0)
│   └── results/                 # Per-condition × per-network eval outputs
│
├── socialmembench/              # Generation infrastructure + smb CLI
│   ├── schemas/                 # Pydantic data contracts (persona, conversation, qa)
│   ├── pipeline/                # Scale planner
│   ├── utils/                   # Manifest, metrics, serialization
│   └── cli/                     # smb command-line tool
│
├── eval/                        # Evaluation pipeline
│   ├── adapters/                # cognee, graphiti, langmem, mem0, naive_rag, subject_rag, smg, llm
│   ├── core/                    # Evaluator, answerer, data bridge
│   └── config/                  # YAML configs per adapter
│
├── skills/                      # Generation specs (read by Claude / human / either)
├── scripts/                     # Reusable build, fix, validate, backfill utilities
├── figures/                     # Paper figures + generator
├── viewer/                      # Interactive web viewer for the dataset
└── paper/                       # NeurIPS 2026 paper sources
```

## Citation

```bibtex
@misc{socialmembench2026,
  title  = {SocialMemBench: Evaluating AI Memory Architectures in Social Group Conversations},
  author = {Anonymous},
  year   = {2026}
}
```

See [CITATION.cff](CITATION.cff) for machine-readable metadata.

## License

Dataset and accompanying code released under [CC BY 4.0](LICENSE). Attribution is the only requirement; commercial and derivative use is permitted.
