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
**These files are the authoritative source for all data generation.** Always read and follow the relevant skill before generating or modifying any data file. Do not generate data by hand — invoke the skill and follow its steps.

How to invoke: read `.claude/commands/{skill-name}.md` and execute its instructions inline. The Skill tool does not support project commands; Claude executes them directly.

**Always run `smb-verify` after Stage 2 and `smb-qc` after Stage 3.** Do not skip verification.

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

## Data Quality Rule

**Any data improvement work must be paired with verifier skill updates.**

If you change what "good data" looks like — new quality dimensions, new realism standards, new structural requirements — update `smb-qc.md` and/or `smb-verify.md` to check for those properties before touching the data. The verification loop (structural gate → QA regression gate → conversation quality check) must always reflect the current quality bar.

This means: raise the bar in the skills first, then improve the data to meet it.

---

## Documentation Style

**Always keep this file lean and high-level.** Do not add implementation details to `CLAUDE.md` — those go in the relevant `plans/` file. When starting a new phase of work, create or update the matching plan file first, then update `CLAUDE.md`'s "Current Status" section only.

---

## Submission Target

**NeurIPS 2026 Evaluations & Datasets Track**
- Abstract deadline: **May 4, 2026** (AoE)
- Full paper deadline: **May 6, 2026** (AoE)
- Portal opens: April 15, 2026 (already open)
- Author notification: September 24, 2026
- Link: https://neurips.cc/Conferences/2026/CallForEvaluationsDatasets 

**Submission requirements:**
- Dataset hosted on Hugging Face (or Dataverse/Kaggle/OpenML) — accessible to reviewers without permission request
- Croissant machine-readable metadata (core + Responsible AI fields)
- Double-blind by default; dataset track may opt into single-blind if anonymization is infeasible
- Code required since benchmark suite is the primary artifact
- Framing must articulate how the work **changes or enables evaluation of AI/ML systems** — not just "new dataset"

**We have ~2 weeks to full submission.**

---

## Current Status

**Done**: 36 networks, 603 QA pairs. 17 small-tier, 16 medium-tier, 3 large-tier. Oracle evals (Condition A) running/complete on ~28 networks (all scoring 0.97–1.00). grp_a5b6c7d8 (recreational 9-person, 12 sessions) in Stage 2; grp_b6c7d8e9 (interest_community 9-person, 12 sessions) in Stage 1.

**Immediate priorities** (in order):
1. Fill eval matrix — oracle done for 16 small networks; medium/large networks need all conditions
2. Complete 5 networks in generation pipeline (Stage 2 → verify → QA → QC)
3. HuggingFace dataset upload + Croissant metadata
4. Paper draft — lead with accuracy-vs-group-size curve as the key result
5. Condition B (memory systems) eval runs

**Milestones**:
| Milestone | Target | Status |
|-----------|--------|--------|
| Manual review of small-tier QA | Confirm data quality | Done |
| Tier validation | 1 medium + 1 large passing QC | Done |
| Condition A oracle (small tier) | Establish ceiling | Done (mean ~1.0) |
| 500 QA pairs | Scale target | Done (603) |
| Eval matrix complete (36 networks) | All conditions × all networks | In progress |
| HuggingFace + Croissant upload | Submission requirement | Before May 4 |
| Paper draft | 3 conditions, full analysis, SMG as direction | Before May 4 |
| Condition B (memory systems) | Primary contribution | Before May 4 |
| Full dataset (46 networks, ~1,650 QA) | Post-submission stretch goal | Post-NeurIPS |
