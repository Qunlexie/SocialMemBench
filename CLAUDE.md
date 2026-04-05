# SocialMemBench

## The Problem

Every AI embedded in a group chat uses a single-stream memory that conflates all members. When Sarah says "Mike hates steep trails," the AI must attribute this to Mike — not Sarah, not the group. No current system does this reliably.

This is not a niche failure. It happens across close friends, families, recreational clubs, interest communities, and acquaintance networks. The consequences: wrong preferences attributed to the wrong person, group norms mistaken for individual preferences, and opinions that changed over time treated as fixed.

## What This Project Is

A benchmark for evaluating AI memory systems in social group settings — not just raw model recall, but deployed memory architectures (Mem0, Letta, LangMem, MemGPT) under realistic conditions. The full pipeline:

1. **Generate** synthetic group conversations with hidden ground-truth memory challenges
2. **Evaluate** memory systems session-by-session against those challenges (8 query types, Q1–Q8)
3. **Score and analyze** where systems fail — and why, architecturally

## Research Positioning

The closest prior work is **EverMemBench** (Feb 2026) — the first multi-party group memory benchmark. Key finding: oracle models score only 26% on multi-hop attribution in workplace settings. We go beyond this in two ways: (1) we target memory systems, not raw LLMs, and (2) social group settings violate every architectural assumption those systems make.

**No benchmark currently evaluates memory systems in social group settings.** This is the gap.

### Key References
- Paper: https://arxiv.org/pdf/2602.01313
- Dataset: https://huggingface.co/datasets/EverMind-AI/EverMemBench-Dynamic/viewer/dialogues/train
- GitHub: https://github.com/EverMind-AI/EverMemBench

## 8 Query Types

| ID | What it tests |
|----|--------------|
| Q1 | Single-contact recall — one person's implicit preference |
| Q2 | Group decision recall — decision + who dissented |
| Q3 | Multi-contact aggregation — all members' preferences on one domain |
| Q4 | Contamination probe — correct attribution when two speakers are confusable |
| Q5 | Theory-of-mind reference — what A revealed about B's preference |
| Q6 | Norm vs. individual — whether a group norm truly applies to everyone |
| Q7 | Relational edge query — relationship history revealed in conversation |
| Q8 | Temporal preference evolution — how a preference changed across sessions |

---

## Where Things Live

### Plans (`plans/`)
Read before working on any phase. Each plan covers one stage of the project:
- [`plans/data-gen.md`](plans/data-gen.md) — Stages 1–3: ego network generation, conversation synthesis, QA generation. Covers the skill-based pipeline and the API→skill pivot.
- [`plans/evaluation.md`](plans/evaluation.md) — Stages 4–5: memory system evaluation, scoring, analysis. Covers the three conditions (oracle / memory system / + social graph), failure mode hypotheses, and reviewer differentiation from EverMemBench.

### Skills (`.claude/commands/`)
Generation pipeline — no API key needed, Claude Code runs these directly:
- `smb-generate-network.md` — Stage 1: ego network
- `smb-generate-conversations.md` — Stage 2: WhatsApp-style conversation corpus
- `smb-generate-qa.md` — Stage 3: Q1–Q8 QA pairs
- `smb-verify.md` — structural verification (all 3 stages)
- `smb-qc.md` — blind critic QC on QA pairs
- `smb-status.md` — manifest summary + progress

Evaluation skills (to build after data gen):
- `smb-evaluate.md` — Stage 4: run a condition against generated QA
- `smb-score.md` — Stage 5: LLM-as-judge scoring + breakdown
- `smb-compare.md` — Stage 5: head-to-head condition comparison

### Schemas (`socialmembench/schemas/`)
Pydantic spec documents — define what JSON the skills must produce. Read before touching data formats:
- `persona.py` — `EgoNetwork`, `Persona`, `RelationshipEdge`, `GroupNorm`
- `conversation.py` — `ConversationCorpus`, `ConversationTurn`, `PlantedChallenge`
- `qa.py` — `QAPair`, `EvidenceAnchor` (Q1–Q8)

### Utilities (`socialmembench/utils/`)
- `manifest.py` — incremental tracking (seeds, consumed challenges, counts per type)
- `serialization.py` — JSON/JSONL I/O
- `metrics.py` — `python -m socialmembench.utils.metrics --data_dir data/`

### Data (`data/`)
- `manifest.json` — auto-managed by skills, do not edit manually
- `raw/` — Stage 1: ego networks
- `conversations/` — Stage 2: conversation corpora
- `qa/` — Stage 3: QA pairs (append-only JSONL)
- `verify/` — verification + QC reports
- `results/` — Stage 4: evaluation outputs (one dir per condition)

---

## Documentation Style

**Always keep this file lean and high-level.** Do not add implementation details to `CLAUDE.md` — those go in the relevant `plans/` file. When starting a new phase of work, create or update the matching plan file first, then update `CLAUDE.md`'s "Current Status" section only.

This structure ensures any future conversation can orient immediately: `CLAUDE.md` for the big picture, `plans/` for the how.

---

## Current Status

**Done**: Data generation pipeline (Stages 1–3) — skills, schemas, manifest.

**Next**: Generate 50 conversations + 100 QA pairs → manual review → design evaluation protocol → Stages 4–5.

**Milestones**:
| Milestone | Goal |
|-----------|------|
| 50 conversations, 100 QA | Validate data quality, manual review |
| Condition A (oracle) | Establish ceiling performance |
| Condition B (memory systems) | Primary contribution — failure mode analysis |
| Paper-ready | 2,000+ QA, 3 conditions evaluated, full analysis |
