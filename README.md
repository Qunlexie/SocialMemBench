# SocialMemBench

A synthetic benchmark for evaluating AI memory architectures in multi-party social group conversations.

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)

## What this benchmark tests

Existing memory benchmarks evaluate either (a) language model reasoning given long context (LongMemEval, RULER), or (b) single-user / dyadic dialogue (LaMP, LoCoMo, MSC). **SocialMemBench is the first benchmark that evaluates external memory systems — the write/index/retrieve substrate between sessions — in social group settings with 3+ co-present speakers.**

The benchmark exposes architectural failures that single-stream memory designs (Mem0, LangMem, Cognee, Graphiti) make when faced with multi-party attribution, group-norm vs. individual preference distinctions, and preference evolution across sessions.

## Dataset summary

- **43 ego networks** spanning 5 social-group types (close friends, family, recreational clubs, interest communities, acquaintance networks)
- **1,033 question–answer pairs** across 9 query types (Q1–Q9)
- **3 size tiers**: small (4–6 members), medium (8–14), large (15–30)
- **9 query types** probing single-contact recall, group decisions, multi-contact aggregation, attribution under contamination, theory-of-mind, group-norm vs. individual, relational edges, temporal preference evolution, and departed-member recall
- **Blind-critic dataset quality**: corpus-wide mean 0.952, 99.9% pass-rate (≥0.70), 1 pair below 0.70
- All conversations validated to be em-dash-free and to preserve ground-truth challenge anchors

## Repository layout

```
.
├── data/
│   ├── manifest.json            # central manifest (auto-managed)
│   ├── raw/                     # Stage 1: ego networks
│   ├── conversations/           # Stage 2: WhatsApp-style corpora
│   ├── qa/                      # Stage 3: QA pairs + QC reports
│   ├── verify/                  # structural verification reports (canonical schema 2.0)
│   └── results/                 # eval outputs per condition
│
├── socialmembench/              # data generation infrastructure (Pydantic schemas, manifest, planner, smb CLI)
│   ├── schemas/                 # data contracts: persona, conversation, qa
│   ├── pipeline/                # scale planner
│   ├── utils/                   # manifest, metrics, serialization
│   └── cli/                     # smb command-line tool
│
├── eval/                        # evaluation pipeline (8 memory-system adapters + judge)
│   ├── adapters/                # cognee, graphiti, langmem, mem0, naive_rag, subject_rag, smg, llm
│   ├── core/                    # evaluator, answerer, data bridge
│   └── config/                  # YAML configs per adapter
│
├── scripts/                     # reusable utilities (build_hf_dataset, build_croissant, recompute_bootstrap, etc.)
├── figures/                     # paper figures + generator
├── viewer/                      # interactive web viewer for the dataset
├── paper/                       # NeurIPS 2026 paper sources
├── docs/                        # research notes and literature
├── plans/                       # working planning documents
└── skills/            # Claude Code skills used to drive generation
```

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

## Data shape

Four logical tables when loaded via `scripts/build_hf_dataset.py`:

- **networks** — one row per ego network (network_id, group_type, group_size, sessions, etc.)
- **personas** — one row per persona, indexed by network_id (communication_profile, big_five, preferences, speaking_quirks)
- **conversations** — one row per turn (network_id, session_index, turn_index, speaker, message, timestamp)
- **qa** — one row per QA pair (qa_id, network_id, query_type, question, answer, evidence_anchors, qc_phase1_score)

Source files on disk are JSON / JSONL; HuggingFace release is parquet with auto-generated Croissant metadata.

## Reproducing the evaluations

Memory system adapters live in `eval/adapters/`. Each adapter has a YAML config in `eval/config/adapters/`. To run an evaluation:

```bash
pip install -e .                       # installs the socialmembench package + smb CLI
python -m eval.cli --condition graphiti --network grp_a0b1c2d3
```

Reproducibility note: regenerating adapter caches (graphiti / cognee / chroma DBs) from scratch requires API keys (OPENAI / ANTHROPIC) and incurs ~$150–500 in embedding + extraction calls. Final per-pair scores are checked into `data/results/`.

## Generation pipeline

Networks were generated through `skills/smb-*` Claude Code skills (no separate API key needed). The skills are:

```
smb-generate-network         Stage 1: ego network → data/raw/{id}.json
smb-generate-conversations   Stage 2: corpus     → data/conversations/{id}.json
smb-generate-qa              Stage 3: QA pairs   → data/qa/{id}.jsonl
smb-verify                   structural verify   → data/verify/{id}.json
smb-qc                       blind-critic QC     → data/qa/{id}_qc.json
smb-status                   manifest summary
```

Schemas, manifest tracking, and the scale planner are in `socialmembench/`. See [CLAUDE.md](CLAUDE.md) for the full project guide and [`plans/`](plans/) for design documents.

## Citation

If you use this benchmark, please cite:

```bibtex
@misc{socialmembench2026,
  title  = {SocialMemBench: Evaluating AI Memory Architectures in Social Group Conversations},
  author = {Anonymous},
  year   = {2026}
}
```

See [CITATION.cff](CITATION.cff) for machine-readable metadata.

## License

Dataset and generation code released under [CC BY 4.0](LICENSE).
