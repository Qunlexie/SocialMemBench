# Social Memory Graph (SMG) — Architecture Design

## Status: Designed — to be implemented after 50 QA pairs are manually verified.

---

## The Core Problem with Existing Systems

Every current memory system (Mem0, LangMem, Letta, A-MEM, Graphiti) makes the same foundational assumption: **one user, one AI**. Their memory schemas are shaped by this:

- **Mem0**: `{user_id: "mike", memory: "Mike dislikes steep trails"}` — `user_id` isolates, does not attribute
- **LangMem**: entity graph node `{entity: "Mike", attribute: "prefers flat trails"}` — no STATED_BY edge
- **Letta**: archival memory as a text block — no structure at all
- **Graphiti/ZEP**: temporal KGs with validity windows — temporal, but not multi-party

None have a concept of **who said what about whom**. In a group chat, that distinction is everything:
- Mike says "my knees still haven't forgiven that last climb" → self-disclosed preference (Q1)
- Sarah says "Mike always bails on hilly routes" → third-party attribution (Q5)
- The group says "we always do Saturdays" but Mike never confirms → implied dissent (Q6)

The Social Memory Graph makes this tripartite attribution structure first-class.

---

## Graph Schema

### Node Types

| Node | Key Properties | Purpose |
|------|---------------|---------|
| `Persona` | `id`, `name`, `group_id` | Represents a group member |
| `PreferenceFact` | `id`, `domain`, `value`, `implicitness` (1–3), `session_id`, `confidence` | A specific belief/preference signal |
| `GroupNorm` | `id`, `norm_text`, `truly_universal`, `session_id` | A norm stated as applying to the group |
| `RelationshipState` | `id`, `closeness`, `sentiment`, `session_id` | Snapshot of a dyadic relationship at a given session |

### Edge Types

| Edge | Direction | Key Properties | Purpose |
|------|-----------|---------------|---------|
| `STATED_PREFERENCE` | `Persona → PreferenceFact` | `speaker_id`, `subject_id`, `session_id`, `turn_idx`, `implicitness` | **Core attribution edge** — who said it, about whom, when |
| `HAS_PREFERENCE` | `Persona → PreferenceFact` | — | Marks the *subject* of this preference fact |
| `KNOWS_PREFERENCE` | `Persona → PreferenceFact` | `session_id`, `confidence` | Speaker demonstrated awareness of someone else's preference (ToM) |
| `EVOLVED_FROM` | `PreferenceFact → PreferenceFact` | `session_id`, `shift_type` | New preference supersedes old; causal chain preserved |
| `DISSENTS_FROM` | `Persona → GroupNorm` | `session_id`, `signal_type` | Persona rejected or hedged on a group norm |
| `ENDORSES` | `Persona → GroupNorm` | `session_id` | Persona affirmed this norm |
| `HAS_RELATIONSHIP` | `Persona ↔ Persona` | `closeness`, `sentiment`, `history_summary`, `session_id` | Dyadic relationship, updated per session |

`DISSENTS_FROM.signal_type` values: `"explicit_reject"`, `"qualifier"`, `"silence"`, `"topic_change"`

### The Tripartite Attribution Structure

Every preference fact sits in a three-node pattern:

```
speaker_persona --[STATED_PREFERENCE]--> PreferenceFact <--[HAS_PREFERENCE]-- subject_persona
```

When `speaker == subject`: self-disclosed (Mike says "I hate hilly routes").  
When `speaker != subject`: third-party attribution (Sarah says "Mike always bails on hills").  
When neither speaker ID matches subject: group inference (silence, consensus).

This is what makes Q4 and Q5 tractable as graph queries rather than string matching.

---

## How Q1–Q8 Map to Graph Traversals

| Query | Traversal Pattern | Failure mode it fixes |
|-------|------------------|----------------------|
| **Q1** single-contact recall | `Persona[X] → [HAS_PREFERENCE] → PreferenceFact[domain=D]` filtered to `STATED_PREFERENCE.speaker == X` | — (baseline) |
| **Q2** group decision recall | `GroupNorm` in session range → return `norm_text` + `DISSENTS_FROM` edges | Norm universalization |
| **Q3** multi-contact aggregation | All `Persona` in group → `[HAS_PREFERENCE]` → `PreferenceFact[domain=D]`; group by persona | Preference conflation |
| **Q4** contamination probe | `Persona[X] → [HAS_PREFERENCE] → PreferenceFact`; validate `STATED_PREFERENCE.speaker_id == X.id`; reject facts where speaker is the foil | Attribution collapse |
| **Q5** theory-of-mind | `Persona[A] → [KNOWS_PREFERENCE] → PreferenceFact → [HAS_PREFERENCE] → Persona[B]` where `A ≠ B` | Attribution collapse |
| **Q6** norm vs. individual | `GroupNorm[norm~=Q]` → check `DISSENTS_FROM` edges → dissenters + signal types | Norm universalization |
| **Q7** relational edge | `HAS_RELATIONSHIP(Persona[A], Persona[B])` across sessions | Relationship ignorance |
| **Q8** temporal evolution | `PreferenceFact` chain via `EVOLVED_FROM` ordered by `session_id` | Temporal blindness |

---

## Insertion Pipeline

For each conversation session, processed in order (session 1 → session N):

**Step 1 — Parse**: Extract `(speaker, content, session_id, turn_idx)` per turn.

**Step 2 — LLM Extraction Pass**: Prompt Claude Opus 4.6 over a sliding window of 3–5 turns:

```
Given this conversation window (group members: {persona_names}):

Extract the following:
1. PREFERENCE_SIGNALS: [{speaker, subject, domain, value, implicitness, evidence_quote}]
   implicitness: 1=explicit ("I hate X"), 2=complaint/behavior ("my knees haven't recovered"),
                 3=silence/deflection/topic-change
2. TOM_SIGNALS: [{knower, subject, domain, value}]
   — when person A reveals they know person B's preferences
3. NORM_STATEMENTS: [{speaker, norm_text, scope: "group"|"some"|"I think"}]
4. NORM_DISSENTS: [{speaker, norm_ref, signal: "explicit_reject"|"qualifier"|"silence"}]
5. RELATIONSHIP_SIGNALS: [{persona_a, persona_b, signal_type, evidence}]
```

**Step 3 — Graph Upsert**:

For each `PREFERENCE_SIGNAL`:
1. Create `PreferenceFact(subject, domain, value, session_id, implicitness)`
2. Add `STATED_PREFERENCE(speaker → fact, session_id, turn_idx)`
3. Add `HAS_PREFERENCE(subject → fact)`
4. Check for existing `PreferenceFact` for same `(subject, domain)` from earlier sessions.
   If value changed: add `EVOLVED_FROM(new_fact → old_fact, session_id, shift_type="preference_update")`

For each `TOM_SIGNAL`:
1. Find or create `PreferenceFact(subject, domain, value)`
2. Add `KNOWS_PREFERENCE(knower → fact, session_id)`

For each `NORM_STATEMENT`:
1. Create `GroupNorm(norm_text, truly_universal=True, session_id)`
2. Add `ENDORSES(speaker → norm)` for all present speakers not dissenting

For each `NORM_DISSENT`:
1. Find matching `GroupNorm`
2. Add `DISSENTS_FROM(speaker → norm, signal_type)`
3. Set `GroupNorm.truly_universal = False`

For each `RELATIONSHIP_SIGNAL`:
1. Upsert `HAS_RELATIONSHIP(A ↔ B)` with updated `closeness`, `sentiment`, `history_summary`

---

## What SMG Has That No Existing System Has

| Capability | Mem0 | LangMem | Letta | Graphiti | **SMG** |
|-----------|:----:|:-------:|:-----:|:--------:|:-------:|
| Multi-party speakers (N > 2) | ❌ | ❌ | ❌ | ❌ | ✅ |
| Speaker attribution on facts | ❌ | ❌ | ❌ | ❌ | ✅ STATED_PREFERENCE edge |
| Self vs. third-party distinction | ❌ | ❌ | ❌ | ❌ | ✅ speaker_id == subject_id check |
| Theory-of-mind chains (A knows B's pref) | ❌ | ❌ | ❌ | ❌ | ✅ KNOWS_PREFERENCE edge |
| Group norms with dissenter tracking | ❌ | ❌ | ❌ | ❌ | ✅ DISSENTS_FROM edge |
| Causal temporal versioning | ❌ | ❌ | ❌ | partial | ✅ EVOLVED_FROM chain |
| Relationship graph with history | ❌ | ❌ | ❌ | ❌ | ✅ HAS_RELATIONSHIP w/ session history |
| Implicit signal inference (levels 1–3) | ❌ | ❌ | ❌ | ❌ | ✅ implicitness property |

These gaps are not engineering shortfalls — they are structural consequences of the dyadic assumption baked into existing architectures. SMG's contribution is showing that removing that assumption (by making attribution a first-class edge) directly addresses all five SocialMemBench failure modes.

---

## Implementation Path

### Prototype — `socialmembench/smg/` (Python + networkx)

```
SocialMemoryGraph
  .ingest_session(session: ConversationSession) → None
  .query_q1(persona_name, domain) → List[PreferenceFact]
  .query_q5(knower_name, subject_name) → List[ToMChain]
  .query_q6(norm_query) → NormResult
  .query_q8(persona_name, domain) → List[TemporalChain]
  .query(nl_question, query_type) → str   # LLM over retrieved subgraph
  .serialize() → dict
```

Backend: `networkx.MultiDiGraph` (in-memory, loaded per network from `data/conversations/{id}.json`).  
Extraction: Claude Opus 4.6 with adaptive thinking per session window.  
Results: `data/results/condition_c/{id}.jsonl`.

### File Plan

| File | Purpose |
|------|---------|
| `socialmembench/smg/__init__.py` | Package init |
| `socialmembench/smg/graph.py` | `SocialMemoryGraph` + node/edge dataclasses |
| `socialmembench/smg/extractor.py` | LLM extraction pass (session → structured signals) |
| `socialmembench/smg/queries.py` | Q1–Q8 traversal methods |

### Production Direction (beyond paper)

Neo4j backend with Cypher queries. Each Q-type traversal maps directly to a Cypher pattern. Persistent incremental ingestion. The schema above translates 1:1.

---

## Why This Works as a Paper Contribution

Condition B provides the empirical failure diagnosis (per query type, per failure mode).  
Condition C (SMG) provides the empirical fix.  
The accuracy gap B→C *is* the quantitative result.

The SMG is not a production system — it is a proof-of-concept showing that the five failure modes are addressable by a single architectural change: **making speaker attribution a first-class graph edge instead of metadata on a flat memory string**.
