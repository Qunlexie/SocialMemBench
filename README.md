# SocialMemBench

A synthetic benchmark for evaluating AI memory in social group conversations.

---

## Overview

SocialMemBench tests whether AI systems can recall and reason about information from multi-session social group chats — the kind of context that accumulates in friend groups, families, and recreational clubs. Unlike workplace benchmarks (e.g., EverMemBench), this benchmark focuses on the implicit, relationship-rich signals that characterize real social communication.

**5 group types**: close friends · family · recreational clubs · interest communities · acquaintance networks

**8 query types**: single-contact recall · group decision recall · multi-contact aggregation · contamination probe · theory-of-mind reference · norm vs. individual · relational edge · temporal preference evolution

---

## Dataset Format

Three splits mirroring EverMemBench, adapted for social settings:

### `profiles`
One row per persona. Includes communication profile, Big Five personality, preferences (implicit and explicit), preference history, speaking quirks, and relationship metadata.

### `dialogues`
WhatsApp-style group chat sessions. Format: `[Session N, H:MMpm] Name: message`. Each session has hidden `_planted` metadata (stripped before release) that drives QA generation.

### `qars`
Question–answer–reference triples. Each QA pair has a `query_type` (Q1–Q8), difficulty rating (easy/medium/hard), ground-truth answer, and evidence anchors pointing to specific turns.

---

## Generation Pipeline

Data is generated through **Claude Code skill files** — no API key or separate model calls needed. Claude Code reads structured instruction files and writes data directly to disk.

```
/smb-generate-network {group_type} {group_size}   → data/raw/{id}.json
/smb-generate-conversations {id} 5                → data/conversations/{id}.json
/smb-generate-qa {id}                             → data/qa/{id}.jsonl
/smb-verify {id}                                  → data/verify/{id}.json
/smb-qc {id}                                      → data/qa/{id}_qc.json
/smb-status                                       → manifest summary
```

See [`CLAUDE.md`](CLAUDE.md) for the full skill reference and [`PLAN.md`](PLAN.md) for architecture details.

---

## Repository Structure

```
.claude/commands/        # Claude Code skill files (the pipeline)
socialmembench/
  schemas/               # Pydantic data models (spec documents)
  utils/                 # Manifest, serialization, metrics
data/
  manifest.json          # Incremental tracking (auto-managed)
  raw/                   # Stage 1: ego networks
  conversations/         # Stage 2: conversation corpora
  qa/                    # Stage 3: QA pairs
  verify/                # Verification and QC reports
```

---

## Query Types

| ID | Name | What it tests |
|----|------|--------------|
| Q1 | Single-contact recall | One person's implicit preference from conversation history |
| Q2 | Group decision recall | Group decision + whether any individual disagreed |
| Q3 | Multi-contact aggregation | All members' preferences on a single domain |
| Q4 | Contamination probe | Correctly attributing a statement when two speakers are easily confused |
| Q5 | Theory-of-mind reference | Tracking what person A revealed about person B's preference |
| Q6 | Norm vs. individual | Whether a stated group norm actually applies to everyone |
| Q7 | Relational edge query | Relationship history between two members, as revealed in chat |
| Q8 | Temporal preference evolution | How a person's preference changed across sessions |

---

## Scale Targets

| Milestone | QA pairs | Networks |
|-----------|----------|----------|
| Initial (manual review) | 50 | 2–3 |
| First scale | 1,000 | ~20 |
| Full dataset | 2,000+ | 40+ |

---

## Requirements

```
python >= 3.11
pydantic >= 2.0
```

No Anthropic API key needed — generation runs through Claude Code.

---

## Citation

> Work in progress.
