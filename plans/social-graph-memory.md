# Social Memory Graph (SMG) — Architecture Plan

## Status: Planned — baseline evaluation complete, implementation next.

---

## What We Learned From the Baselines

After running 8 conditions (oracle, llm_mini, llm_gemini, naive_rag, mem0_local, graphiti, cognee, langmem) across 10 networks, 77 QA pairs, the results reveal three distinct failure clusters:

| Failure mode | Systems affected | Root cause |
|---|---|---|
| **Attribution collapse** (Q4=0.000) | cognee, langmem | LLM extraction abstracts away speaker identity |
| **Epistemic blindness** (Q5=0.000) | mem0, graphiti, langmem, cognee | No data structure for "A knows B's preference" |
| **Norm universalisation** (Q6=0.000) | mem0, graphiti, langmem | Individual exceptions drowned in group-level summaries |
| **Temporal blindness** (Q7/Q8=0.000) | graphiti, langmem | No ordered retrieval or fact versioning |

The single most important finding: **naive_rag (0.390) outperforms every purpose-built memory system** on the benchmark's hardest social dimensions (Q5=0.505, Q6=0.500). Raw turns stored verbatim — with zero extraction, zero graph, zero consolidation — beat every "smarter" system.

This tells us what is broken. Every extractive/graph/consolidation system loses attribution during its processing step. The extraction layer is the source of failure, not the fix.

---

## The Design Constraint: Not Cheating

naive_rag's advantage rests on two things:

1. **No compression loss** — 5 sessions × 20 turns is a tiny corpus. Cosine search over 100 verbatim turns is nearly lossless at this scale.
2. **Lexical speaker matching** — turns are stored as `[Marcus] message`. When a query mentions Marcus, string overlap does the attribution work without any semantic understanding.

SMG must not rely on either of these. Specifically:

**Rule 1 — No verbatim turn storage.**
SMG stores extracted facts, not raw turns. This introduces real compression (some information is lost), same as every other extractive system. This is the honest cost.

**Rule 2 — No lexical attribution.**
Q4 retrieval uses embedding similarity over fact *content*, not name matching. The speaker attribution comes from graph edges (structural), not from the word "Marcus" appearing in both the query and the stored text.

**What IS legitimate:**
Speaker identity from the source `speaker_display_name` field is structural input — always known in any chat application (WhatsApp, Slack, iMessage all show who sent each message). Using this structurally is not cheating. It is the architectural insight: don't discard what the data gives you for free by converting it to text and re-inferring it with an LLM.

The failure of mem0, graphiti, cognee, and langmem is exactly this: they receive `(speaker_id, message)` pairs and immediately stringify them into `"[Marcus] my knees still haven't forgiven..."`, then ask an LLM to figure out who Marcus is during extraction. Information that was structural becomes text, then is partially recovered by the LLM, with inevitable loss. SMG keeps it structural end-to-end.

---

## Core Architectural Claim

> Every existing memory system stores facts in a single retrieval pool. Person identity is text metadata, not structure. SMG makes person identity a first-class graph node. Every fact is anchored to the person who holds it via a typed edge. Queries traverse the person node, not the text.

This single change — identity-first graph — directly addresses all four failure modes:

| Failure mode | How SMG addresses it |
|---|---|
| Attribution collapse | Speaker is a graph node. Facts belong to nodes. LLM extracts content; graph preserves who. |
| Epistemic blindness | `KNOWS_ABOUT` edge is a first-class edge type, not derivable from text retrieval. |
| Norm universalisation | `GroupNorm` node separate from `PersonFact` node. Dissenters linked via `DISSENTS_FROM` edge. |
| Temporal blindness | Facts are versioned by session. `EVOLVED_FROM` edges form temporal chains. Current fact is the chain head. |

---

## Differentiation From Each Baseline

### vs. naive_rag
- naive_rag stores raw text; SMG stores extracted structured facts → SMG loses some content but gains queryable structure
- naive_rag attributes via lexical name match; SMG attributes via graph edge → SMG's Q4 retrieval is semantic over content, not over names
- naive_rag cannot answer Q5 (who knows what) or Q6 (group norm exceptions) at all — no structure for these → SMG answers them via graph traversal

### vs. mem0_local
- mem0 extracts to a flat vector store; SMG extracts to a person-attributed graph → same extraction cost, fundamentally different storage
- mem0 loses speaker identity during extraction (Q4=0.037); SMG preserves it structurally (speaker node is set before LLM runs)
- mem0 has no norm or epistemic layer (Q5/Q6=0.000); SMG has explicit GroupNorm and KNOWS_ABOUT nodes

### vs. graphiti
- graphiti builds a temporal KG from episodes; SMG builds a person-attributed fact graph from turns
- graphiti's graph nodes are entities (concepts); SMG's primary nodes are Personas (people)
- graphiti retrieves by querying the graph with natural language → poor recall (Q4=0.125, Q8=0.000); SMG routes queries by person node first, then retrieves facts from that node
- graphiti has no epistemic or norm layer; SMG does

### vs. cognee
- cognee does batch document-level extraction; SMG does turn-level extraction preserving speaker_id
- cognee loses Q4=0.000 because its entity extraction conflates speakers into concept nodes; SMG uses speaker_id as the primary node key
- both build knowledge graphs; SMG's schema is social-domain-specific (Persona, Fact, GroupNorm, Relationship)

### vs. langmem
- langmem consolidates across sessions, merging/updating facts; this erases temporal trajectory (Q8=0.000)
- SMG preserves all versions of a fact via EVOLVED_FROM chains — the old and new values coexist, ordered by session
- langmem's consolidation loses Q4=0.000 (speaker abstracted away); SMG preserves speaker structurally before any LLM runs

---

## Graph Schema

### Node Types

| Node | Key fields | Meaning |
|---|---|---|
| `Persona` | `id`, `name`, `group_id` | A group member. Primary anchor for all facts. |
| `Fact` | `id`, `domain`, `value`, `session`, `implicitness` (1–3), `evidence_quote` | One extracted belief, preference, or state about a person. |
| `GroupNorm` | `id`, `domain`, `value`, `session`, `truly_universal` | A norm stated as applying to the whole group. |
| `Relationship` | `id`, `persona_a`, `persona_b`, `description`, `session` | Dyadic relationship state at a given session. |

### Edge Types

| Edge | From → To | Key fields | Meaning |
|---|---|---|---|
| `HOLDS` | Persona → Fact | `session`, `implicitness` | This person holds this belief/preference. Subject of the fact. |
| `STATED` | Persona → Fact | `session`, `turn_idx` | This person *said* this fact — may be about themselves or another. |
| `KNOWS_ABOUT` | Persona → Fact | `session`, `evidence` | This person demonstrated awareness of another's fact in conversation. |
| `EVOLVED_FROM` | Fact → Fact | `session`, `trigger` | This fact supersedes an earlier one. Forms a temporal chain. |
| `DISSENTS_FROM` | Persona → GroupNorm | `session`, `signal` | This person implicitly or explicitly rejected the norm. |
| `ENDORSES` | Persona → GroupNorm | `session` | This person agreed with or accepted the norm. |
| `RELATED_TO` | Persona ↔ Persona | `description`, `session` | Dyadic relationship, updated per session. |

### The Core Pattern

```
Speaker --[STATED]--> Fact <--[HOLDS]-- Subject
```

When speaker == subject: self-disclosed (`[Marcus] I hate steep trails`)
When speaker != subject: third-party (`[Sarah] Marcus always bails on hilly routes`)

This is the structural difference from every existing system. The LLM extracts the *content* of the fact. The graph records *whose* fact it is — from the data, not from LLM inference.

---

## Insertion Pipeline

For each conversation turn `(speaker_id, speaker_name, message, session_idx, turn_idx)`:

**Step 1 — Speaker node (always deterministic, no LLM)**
```
persona = graph.get_or_create_persona(speaker_id, speaker_name, group_id)
```
This never requires LLM inference. The speaker is always known.

**Step 2 — LLM extraction over a 5-turn sliding window**

Prompt the LLM with the current turn and ±2 surrounding turns for context:

```
Group members: {name_list}
Current speaker: {speaker_name}

Conversation window:
{window_text}

Extract ONLY what is grounded in this window. Return JSON:

{
  "facts": [
    {
      "subject": "<name from member list — who holds this belief>",
      "domain": "<short domain label, e.g. 'trail_difficulty'>",
      "value": "<the belief or preference, 1 sentence>",
      "implicitness": <1|2|3>,
      "evidence_quote": "<exact words from the turn, max 100 chars>",
      "supersedes_domain": "<domain of an earlier fact this contradicts, or null>"
    }
  ],
  "knows_about": [
    {
      "knower": "<who demonstrated knowledge>",
      "subject": "<who the knowledge is about>",
      "domain": "<domain>",
      "evidence_quote": "<exact words showing the knower already knew>"
    }
  ],
  "norm_signals": [
    {
      "type": "assertion|dissent",
      "speaker": "<name>",
      "norm_text": "<1 sentence>",
      "signal": "explicit|qualifier|silence|topic_change"
    }
  ]
}

Rules:
- subject must be a name from the member list
- Do not infer facts not grounded in this window
- implicitness: 1=stated directly, 2=implied by behavior or complaint, 3=silence or deflection
- If no facts are present, return empty arrays
```

**Step 3 — Graph upsert**

For each extracted fact:
1. Create `Fact(domain, value, session, implicitness, evidence_quote)`
2. Add `STATED(speaker_persona → fact)`
3. Find subject persona from name (already in graph as a Persona node)
4. Add `HOLDS(subject_persona → fact)`
5. If `supersedes_domain` is set: find existing `Fact` for `(subject, supersedes_domain)`, add `EVOLVED_FROM(new_fact → old_fact)`

For each `knows_about` signal:
1. Find or create the referenced `Fact`
2. Add `KNOWS_ABOUT(knower_persona → fact, evidence)`

For each `norm_signal`:
1. If assertion: create `GroupNorm(norm_text, session)`, add `ENDORSES(speaker → norm)`
2. If dissent: find matching `GroupNorm`, add `DISSENTS_FROM(speaker → norm, signal)`, set `norm.truly_universal = False`

---

## Query Execution (Q1–Q8)

Each query type maps to a specific graph traversal + optional LLM answer generation.

**Q1 — Single contact recall**
```
facts = graph.get_facts(persona_name=X, domain_hint=Q)
# Returns: all HOLDS edges from X's persona node, filtered by domain similarity
answer = llm_format(facts, question)
```
Semantic search over `fact.value` text — NOT over persona names.

**Q2 — Group decision recall**
```
norm = graph.find_norm(domain_hint=Q)
dissenters = graph.get_dissenters(norm)  # DISSENTS_FROM edges
answer = llm_format(norm, dissenters, question)
```

**Q3 — Multi-contact aggregation**
```
for persona in graph.all_personas(group_id):
    facts = graph.get_facts(persona, domain_hint=Q)
    results[persona.name] = facts
answer = llm_format(results, question)
```

**Q4 — Contamination probe (attribution)**
```
# Embed the question's described statement
query_embedding = embed(statement_description)
# Search fact.value embeddings — NOT persona names
candidate_facts = graph.semantic_search_facts(query_embedding, top_k=5)
# Return persona via HOLDS edge — structural, not textual
answer = candidate_facts[0].held_by.name
```
This is the critical difference from naive_rag. The semantic search is over fact content. The attribution comes from the graph edge. The word "Marcus" need not appear anywhere in the query.

**Q5 — Theory of mind**
```
# Who knows about X's preference on domain D?
subject_facts = graph.get_facts(persona_name=X, domain_hint=D)
knowers = [edge.from_persona for fact in subject_facts
           for edge in graph.get_knows_about_edges(fact)]
answer = llm_format(subject_facts, knowers, question)
```

**Q6 — Norm vs. individual**
```
norm = graph.find_norm(domain_hint=Q)
dissenters = graph.get_dissenters(norm)  # DISSENTS_FROM with signal type
answer = llm_format(norm, dissenters, question)
```

**Q7 — Relational edge**
```
rel = graph.get_relationship(persona_a=A, persona_b=B)
answer = llm_format(rel, question)
```

**Q8 — Temporal evolution**
```
# Traverse EVOLVED_FROM chain for persona X, domain D
chain = graph.get_temporal_chain(persona_name=X, domain_hint=D)
# chain is ordered oldest → newest via EVOLVED_FROM edges
answer = llm_format(chain, question)
```

---

## What SMG Has That No Other System Has

| Capability | naive_rag | mem0 | graphiti | cognee | langmem | **SMG** |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Speaker attribution (structural, not lexical) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Self vs. third-party distinction | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Epistemic layer (who knows B's pref) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Group norm + individual exception | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Temporal fact versioning (chain preserved) | ❌ | ❌ | partial | ❌ | ❌ | ✅ |
| Q4 retrieval without name matching | ❌ | N/A | ❌ | ❌ | N/A | ✅ |
| Designed for N > 2 speakers | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

---

## Implementation Plan

### Phase 1 — Core graph + insertion (no LLM)
- `eval/adapters/smg/graph.py` — node/edge dataclasses + `SocialMemoryGraph` class
- `eval/adapters/smg/insertion.py` — step 1 (persona creation) + step 3 (upsert from structured signals)
- Unit tests: insert known facts, verify HOLDS/STATED/EVOLVED_FROM structure

### Phase 2 — LLM extraction
- `eval/adapters/smg/extractor.py` — sliding window extraction prompt + JSON parse
- Test on 2–3 sessions from a known network; manually verify extracted facts against planted challenges
- Tune prompt until extraction quality is solid before running eval

### Phase 3 — Query execution
- `eval/adapters/smg/queries.py` — Q1–Q8 traversal functions
- `eval/adapters/smg_adapter.py` — `BaseAdapter` implementation wrapping graph + queries

### Phase 4 — Eval run
- `python -m eval.cli --network grp_1a2b3c4d --condition smg`
- Run across all 10 small-tier networks
- Compare to all 8 baseline conditions

### Technology
- **Graph**: `networkx.MultiDiGraph` — pure Python, no install required, sufficient for in-memory eval
- **Embeddings**: OpenAI `text-embedding-3-small` — same as naive_rag, fair comparison
- **Extraction LLM**: `gpt-4o-mini` — same model as mem0/graphiti/cognee for fair comparison
- **Answer LLM**: `gpt-4o` — same as other memory conditions

### What counts as success
SMG should outperform ALL memory systems on Q4, Q5, Q6 specifically. If it doesn't outperform naive_rag on Q4 (given it's not using name matching), something is wrong with the retrieval. Q5 and Q6 are impossible for naive_rag — any non-zero score there is a win.

The paper claim is not "SMG is the best system overall." It is: "SMG is the only system that addresses all four social memory failure modes, and it does so by making person identity structurally first-class rather than textually inferred."
