# Evaluation Plan (Stages 4–5)

## Status: Designed — to be implemented after first 50 conversations are generated and manually verified.

---

## Core Research Question

Do memory systems designed for single-user, dyadic interaction break down when deployed in multi-party social group settings — and if so, in what specific ways?

This is not a question about whether large models can recall long contexts. It is a question about memory architecture: how systems like Mem0, Letta, LangMem, and MemGPT store, index, and retrieve information when multiple speakers with distinct identities, relationships, and evolving preferences are involved.

---

## Beyond EverMemBench — Reviewer Defense

Reviewers will ask: "isn't this just EverMemBench in a social domain?" The answer is no, on four axes:

**1. Evaluation target is different (most important)**
EverMemBench evaluates raw LLMs with the full transcript in context — essentially a reading comprehension test on long documents. We evaluate *memory systems* (Mem0, Letta, LangMem) under realistic deployment conditions — session-by-session ingestion, then retrieval. This is a fundamentally different experimental setup that tests architectural limitations, not model capacity.

**2. Signal type is different**
EverMemBench facts are largely explicit (meeting notes, task assignments, stated decisions). SocialMemBench signals are implicit — revealed through complaints, reactions, silences, and third-party references. An AI must infer "Mike dislikes steep trails" from "my knees still haven't forgiven that last climb." This requires a different kind of memory: not storage and retrieval of stated facts, but inference and attribution of behavioral signals.

**3. Three novel query types with no EverMemBench analog**
- **Q5 (theory-of-mind reference)**: tests whether the system tracks not just what was said, but who said it *about* whom — a two-hop attribution problem
- **Q6 (norm vs. individual)**: tests whether the system can distinguish a group-stated norm from a contested one — requires storing dissenter information, not just the norm text
- **Q8 (temporal evolution)**: tests whether preferences are versioned or overwritten — requires the memory system to maintain a timeline, not a snapshot

**4. We propose a direction, not just a diagnosis**
EverMemBench's conclusion is "models fail." Our conclusion will be "memory systems fail for specific architectural reasons, and here is what a social-aware memory architecture would need to fix them." Condition C (memory + social graph) makes this concrete.

---

## Differentiation from EverMemBench

| Dimension | EverMemBench | SocialMemBench |
|-----------|-------------|----------------|
| Domain | Workplace (meetings, tasks) | Social (friends, family, clubs) |
| Primary target | Raw LLMs (context window) | Memory systems (Mem0, Letta, LangMem) |
| Preference signals | Explicit (stated in meeting notes) | Implicit (behavior, complaints, reactions) |
| Group norms | N/A | Contested — some norms have dissenters |
| Relationships | Hierarchical (manager/report) | Personal, varied closeness + sentiment |
| Preference drift | Rare | Common — opinions evolve across sessions |
| Attribution challenge | Who said what in a meeting | Who implied what about whom, in passing |

---

## Three Evaluation Conditions

**Condition A — Oracle (upper bound)**
Raw LLM receives the full conversation corpus as context. No memory system. Tests whether the information is recoverable in principle. Establishes the ceiling.

**Condition B — Memory system (primary contribution)**
Conversations are processed through a memory system as they arrive, session by session. Queries hit the memory store — not the raw transcript. Tests whether the architecture correctly attributes, stores, and retrieves multi-party social signals.

Target systems: **Mem0**, **Letta** (MemGPT successor), **LangMem**, plus a naive baseline (per-speaker key-value store).

> **Note on graph-based systems**: Letta and LangMem use graph structures, but their graphs model relationships between topics and entities — not between speakers in a group. They still assume a single "user" interacting with the AI. In a group chat, who is the user? The whole group? Each member individually? These systems store "Mike dislikes steep trails" as a fact node — but with no distinction between whether Mike stated it himself (Q1), Sarah stated it about Mike (Q5), or the group inferred it from Mike's silence (Q6). That attribution chain is absent from current architectures and is precisely what Q4/Q5 test.

**Condition C — Memory + social graph (proposed direction)**
Same as B but with an explicit speaker-attributed memory graph: nodes are personas, edges encode relationship type/closeness/sentiment, and every stored preference is tagged with (speaker, subject, session). Tests whether adding social structure fixes the Condition B failures. This becomes the paper's forward-looking contribution.

---

## Expected Failure Modes (hypotheses)

| Failure mode | Query types it surfaces | Why it happens |
|-------------|------------------------|----------------|
| Attribution collapse | Q4 (contamination), Q5 (ToM) | Facts stored without strong speaker binding |
| Norm universalization | Q6 (norm vs. individual) | No concept of "group-stated but individually contested" |
| Preference conflation | Q3 (multi-contact) | Multiple speakers' preferences merged into one entry |
| Temporal blindness | Q8 (temporal evolution) | Memory overwrites rather than versions preferences |
| Relationship ignorance | Q7 (relational edge) | No relationship graph; history not stored as edge properties |

---

## Scoring

LLM-as-judge (Claude scores 0.0–1.0 per pair):
- **1.0**: correct attribution + correct preference + complete answer
- **0.5–0.9**: partially correct (right preference, wrong speaker; or right speaker, incomplete)
- **0.0–0.4**: wrong attribution, wrong preference, or hallucinated evidence

Calibrate against manual scores on the 100-pair pilot before applying at scale.

---

## Skills to Build (Stage 4–5)

**`smb-evaluate.md`** — `/smb-evaluate {condition} {network_id}`
- Condition A: full corpus → LLM → answer
- Condition B: session-by-session ingestion → memory API → query → answer
- Writes to `data/results/{condition}/{network_id}.jsonl`

**`smb-score.md`** — `/smb-score {condition}`
- LLM-as-judge per pair
- Breakdown: per query type, per difficulty, per group type
- Failure mode classification for each wrong answer

**`smb-compare.md`** — `/smb-compare {condition_a} {condition_b}`
- Head-to-head accuracy table
- Delta per query type — where does the memory system lose relative to oracle?
- Failure mode comparison across conditions

---

## Milestones

| Milestone | Action |
|-----------|--------|
| 50 conversations, 100 QA generated | Manual review — validate data quality |
| Evaluation design locked | Confirm memory system APIs, finalize scoring rubric |
| Condition A (oracle) | Establish ceiling; check Q5/Q6 are non-trivial |
| Condition B (memory systems) | Primary contribution data |
| Condition C (+ social graph) | Proposed direction evidence |
| Analysis complete | Failure mode table, per-type accuracy, delta vs oracle |
| Paper | Full results + proposed social graph memory architecture |
