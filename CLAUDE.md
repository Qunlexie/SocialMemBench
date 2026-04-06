# SocialMemBench

## The Problem

Every AI embedded in a group chat uses a single-stream memory that conflates all members. When Sarah says "Mike hates steep trails," the AI must attribute this to Mike — not Sarah, not the group. No current system does this reliably.

This is not a niche failure. It happens across close friends, families, recreational clubs, interest communities, and acquaintance networks. The consequences: wrong preferences attributed to the wrong person, group norms mistaken for individual preferences, and opinions that changed over time treated as fixed.

## What This Project Is

A benchmark for evaluating AI memory systems in social group settings — not just raw model recall, but deployed memory architectures (Mem0, Letta, LangMem) under realistic conditions. The full pipeline:

1. **Generate** synthetic group conversations with hidden ground-truth memory challenges
2. **Evaluate** memory systems session-by-session against those challenges (Q1–Q9)
3. **Score and analyze** where systems fail — and why, architecturally

## Research Positioning

The closest prior work is **EverMemBench** (Feb 2026) — the first multi-party group memory benchmark. Key finding: oracle models score only 26% on multi-hop attribution in workplace settings. We go beyond this in two ways: (1) we target memory systems, not raw LLMs, and (2) social group settings violate every architectural assumption those systems make.

**No benchmark currently evaluates memory systems in social group settings.** This is the gap.

### Key References
- Paper: https://arxiv.org/pdf/2602.01313
- Dataset: https://huggingface.co/datasets/EverMind-AI/EverMemBench-Dynamic/viewer/dialogues/train
- GitHub: https://github.com/EverMind-AI/EverMemBench

## Query Types

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
| Q9 | Departed member recall — last known preference of a member who left the group |
| Q8L | *(longitudinal extension)* Multi-stage preference evolution traced over years |

Q9 and Q8L are only generated for networks where departure and longitudinal timespan are modelled respectively.

## Experimental Variables

Group size, timespan, noise level, and membership dynamics are **first-class variables** — not just parameters. Each produces a distinct paper result:

| Variable | Range | Paper result |
|----------|-------|-------------|
| Group size | 3–6 / 7–14 / 15–30 | Q1–Q9 accuracy curve vs. group size |
| Timespan | 5 weeks / 3 months / 3 years | Memory decay and multi-stage evolution |
| Noise level | low / medium / high | Accuracy degradation as signal-to-noise drops |
| Member departure | none / sparse / common | Stale recall and post-departure false attribution |

See `plans/data-gen.md` for the full design of each variable.

---

## Where Things Live

### Plans (`plans/`)
Read before working on any phase:
- [`plans/data-gen.md`](plans/data-gen.md) — Dataset design, experimental variables, generation pipeline, scale targets
- [`plans/evaluation.md`](plans/evaluation.md) — Three evaluation conditions (oracle / memory system / social graph), scoring, failure mode hypotheses, EverMemBench differentiation
- [`plans/social-graph-memory.md`](plans/social-graph-memory.md) — Social Memory Graph (Condition C): graph schema, Q1–Q9 traversal patterns, insertion pipeline, implementation plan

### Skills (`.claude/commands/`)
Generation pipeline — no API key needed, Claude Code runs these directly:
- `smb-generate-network.md` — Stage 1: ego network
- `smb-generate-conversations.md` — Stage 2: WhatsApp-style conversation corpus
- `smb-generate-qa.md` — Stage 3: Q1–Q9 QA pairs
- `smb-verify.md` — structural verification (all 3 stages)
- `smb-qc.md` — blind critic QC on QA pairs
- `smb-status.md` — manifest summary + progress

Evaluation skills (to build after small-scale validation):
- `smb-evaluate.md` — Stage 4: run a condition against generated QA
- `smb-score.md` — Stage 5: LLM-as-judge scoring + breakdown
- `smb-compare.md` — Stage 5: head-to-head condition comparison

### Schemas (`socialmembench/schemas/`)
Pydantic spec documents — define what JSON the skills must produce. Read before touching data formats:
- `persona.py` — `EgoNetwork`, `Persona`, `RelationshipEdge`, `GroupNorm`
- `conversation.py` — `ConversationCorpus`, `ConversationSession`, `ConversationTurn`, `PlantedChallenge`
- `qa.py` — `QAPair`, `EvidenceAnchor` (Q1–Q9)

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

---

## Current Status

**Done**: 10 small-tier networks, 77 QA pairs (all stage3_done). Schema updated for group size tiers, longitudinal timespan, noise level, participation rate, and member departure. Data viewer built (`viewer/`).

**Immediate next step**: Manual review of existing 77 QA pairs. Validate data quality and confirm planted signals are genuinely implicit before scaling further.

**Then**: Generate 1 medium-tier and 1 large-tier network → validate Q8 viability at those tiers → run Condition A oracle on the reviewed QA → confirm hypothesis → scale.

**Milestones**:
| Milestone | Goal |
|-----------|------|
| Manual review of 77 QA | Confirm data quality; Q4/Q5/Q6 are non-trivial |
| Tier validation (15 networks) | 1 medium + 1 large passing QC |
| Condition A oracle | Establish ceiling; validate hypothesis |
| First scale (25 networks, ~800 QA) | Small + medium tiers complete |
| Condition B (memory systems) | Primary contribution — failure mode analysis |
| Full dataset (46 networks, ~1,650 QA) | Large + longitudinal tiers; all variables covered |
| Paper-ready | 3 conditions evaluated, full analysis, SMG as proposed direction |
