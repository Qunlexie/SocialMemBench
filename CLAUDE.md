# SocialMemBench

## The Problem

Every AI embedded in a group chat uses a single-stream memory that conflates all members. When Sarah says "Mike hates steep trails," the AI must attribute this to Mike — not Sarah, not the group. No current system does this reliably.

This is not a niche failure. It happens across close friends, families, recreational clubs, interest communities, and acquaintance networks. The consequences: wrong preferences attributed to the wrong person, group norms mistaken for individual preferences, and opinions that changed over time treated as fixed.

## What This Project Is

A benchmark for evaluating AI social memory across five group types, using synthetic WhatsApp-style conversations with controlled planted memory challenges. The full pipeline:

1. **Generate** synthetic group conversations with hidden ground-truth memory challenges
2. **Evaluate** AI models against those challenges (8 query types, Q1–Q8)
3. **Score and analyze** where models succeed and fail across social memory dimensions

## Research Positioning

The closest prior work is **EverMemBench** (Feb 2026) — the first multi-party group memory benchmark. Key finding: oracle models score only 26% on multi-hop attribution. But EverMemBench is locked to workplace/enterprise settings. Social groups are structurally different: relationships are personal, norms have dissenters, preferences are rarely stated directly, and opinions shift over time.

**No benchmark currently covers social group memory.** This is the gap.

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

### Plans
Detailed implementation plans — read these before working on any stage:
- [`plans/data-gen.md`](plans/data-gen.md) — Stage 1–3 data generation pipeline (built). Documents the original API approach and the pivot to Claude Code skill files.
- [`plans/evaluation.md`](plans/evaluation.md) — Stage 4–5 model evaluation and scoring (planned, to be designed after first 50 conversations).

### Skills (`.claude/commands/`)
The generation pipeline runs through Claude Code skill files — no API key needed:
- `smb-generate-network.md` — Stage 1: generate one ego network
- `smb-generate-conversations.md` — Stage 2: generate WhatsApp-style conversation corpus
- `smb-generate-qa.md` — Stage 3: generate Q1–Q8 QA pairs from planted challenges
- `smb-verify.md` — structural verification across all 3 stages
- `smb-qc.md` — blind critic QC on QA pairs
- `smb-status.md` — manifest summary + progress

### Schemas (`socialmembench/schemas/`)
Pydantic data models — these are the spec documents that define exactly what JSON the skills must produce. Read before modifying data formats:
- `persona.py` — `EgoNetwork`, `Persona`, `RelationshipEdge`, `GroupNorm`
- `conversation.py` — `ConversationCorpus`, `ConversationTurn`, `PlantedChallenge`
- `qa.py` — `QAPair`, `EvidenceAnchor`, query types Q1–Q8

### Utilities (`socialmembench/utils/`)
- `manifest.py` — `DatasetManifest`: incremental tracking (seeds, consumed challenges, counts). Read by every skill before generating; updated after.
- `serialization.py` — JSON/JSONL I/O helpers
- `metrics.py` — quality metrics: `python -m socialmembench.utils.metrics --data_dir data/`

### Data (`data/`)
- `manifest.json` — auto-managed by skills, do not edit manually
- `raw/` — Stage 1 outputs: one JSON per network
- `conversations/` — Stage 2 outputs: one JSON per network
- `qa/` — Stage 3 outputs: one JSONL per network (append-only)
- `verify/` — verification + QC reports
- `results/` — Stage 4 outputs: model evaluation results (one directory per model)

---

## Current Status and Next Steps

**Done**: Data generation pipeline (Stages 1–3) — skill files, schemas, manifest infrastructure.

**Immediate next step**: Generate 50 conversations + 100 QA pairs, manually verify quality, then design the evaluation protocol.

**Run order for first network**:
```
/smb-generate-network recreational 3
/smb-verify {id} --stage 1
/smb-generate-conversations {id} 5
/smb-verify {id} --stage 2
/smb-generate-qa {id}
/smb-qc {id}
/smb-verify {id} --stage 3
/smb-status
```

**Milestones**:
| Milestone | Goal |
|-----------|------|
| 50 conversations, 100 QA | Manual review + first evaluation run |
| 1,000 QA pairs | Full data gen, 2–3 models evaluated |
| Paper-ready | 2,000+ QA, full analysis, comparison to EverMemBench |
