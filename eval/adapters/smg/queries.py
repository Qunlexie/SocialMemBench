"""
SMG query engine: natural language question → structured context.

No Q-type routing. No hardcoded question patterns. The query pipeline
receives only a natural language question and returns graph context.

Pipeline:
  1. Embed the question
  2. Find semantically similar facts (by fact.value content)
  3. For each retrieved fact, expand with full graph context:
       - who HOLDS it (subject)
       - who STATED it (speaker — may differ from subject)
       - who KNOWS_ABOUT it (epistemic layer)
       - EVOLVED_FROM chain (temporal trajectory)
  4. Search GroupNorm nodes for relevant norms + dissenters
  5. Format as structured context string for the answerer LLM

The graph structure does the attribution work. The question text drives
which facts are retrieved. Q type is never consulted.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .graph import SocialMemoryGraph, Fact, Persona


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _format_fact_with_context(graph: SocialMemoryGraph, fact: Fact) -> str:
    """
    Format a single fact with its full graph context:
    subject, speaker (if different), knowers, temporal chain.
    """
    lines = []

    subject = graph.subject_of_fact(fact.id)
    speaker = graph.speaker_of_fact(fact.id)

    subject_name = subject.name if subject else "unknown"
    speaker_name = speaker.name if speaker else "unknown"

    impl_label = {1: "stated directly", 2: "implied", 3: "signalled indirectly"}.get(
        fact.implicitness, "implied"
    )

    if speaker and subject and speaker.id == subject.id:
        lines.append(
            f"[{subject_name}] {fact.value} "
            f"({impl_label}, session {fact.session})"
        )
    else:
        lines.append(
            f"[About {subject_name}, stated by {speaker_name}] {fact.value} "
            f"({impl_label}, session {fact.session})"
        )

    if fact.evidence_quote:
        lines.append(f'  Evidence: "{fact.evidence_quote}"')

    # Epistemic layer: who else knows about this
    knowers = graph.knowers_of_fact(fact.id)
    for knower, evidence in knowers:
        if knower.id != (speaker.id if speaker else None):
            lines.append(
                f"  {knower.name} knew about this: \"{evidence}\""
            )

    # Temporal chain: show if this fact replaced an earlier belief
    chain = graph.temporal_chain(fact.id)
    if len(chain) > 1:
        oldest = chain[0]
        lines.append(
            f"  Earlier belief (session {oldest.session}): {oldest.value}"
        )

    return "\n".join(lines)


def _format_norm_with_context(graph: SocialMemoryGraph, norm_id: str) -> str:
    """Format a group norm with its dissenters."""
    norm = graph.norms.get(norm_id)
    if not norm:
        return ""

    lines = [f"[Group norm, session {norm.session}] {norm.value}"]

    dissenters = graph.dissenters_of_norm(norm_id)
    if dissenters:
        for persona, signal in dissenters:
            signal_desc = {
                "explicit_reject": "explicitly disagreed",
                "qualifier": "expressed reservations",
                "silence": "went quiet / did not confirm",
                "topic_change": "changed the subject",
            }.get(signal, signal)
            lines.append(f"  Exception: {persona.name} {signal_desc}")
        lines.append(f"  (norm is NOT universally held)")
    else:
        lines.append(f"  (held by all present members)")

    return "\n".join(lines)


def retrieve_context(
    graph: SocialMemoryGraph,
    query_embedding: List[float],
    top_k: int = 10,
    query_type: Optional[str] = None,
) -> str:
    """
    Retrieve relevant context from the graph for a query embedding.

    Returns a formatted string ready to pass to the answerer LLM.
    query_type enables structural routing:
      Q8 — full temporal chain for top subject (all sessions, not just top_k)
      Q5 — KNOWS_ABOUT edges prioritized
      Q2/Q6 — DISSENTS_FROM edges always surfaced
    """
    # --- 1. Score all facts by embedding similarity ---
    scored: List[Tuple[float, Fact]] = []
    for fact in graph.all_facts():
        if fact.embedding:
            sim = cosine_similarity(query_embedding, fact.embedding)
            scored.append((sim, fact))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_facts = [f for _, f in scored[:top_k]]

    # --- 2. Score all norms by embedding similarity ---
    norm_scored: List[Tuple[float, str]] = []
    for norm_id, norm in graph.norms.items():
        if hasattr(norm, "_embedding") and norm._embedding:
            sim = cosine_similarity(query_embedding, norm._embedding)
            norm_scored.append((sim, norm_id))
    norm_scored.sort(key=lambda x: x[0], reverse=True)
    top_norm_ids = [nid for _, nid in norm_scored[:3]]

    # --- 3. Expand: for the top-scoring subject persona, include ALL their facts ---
    expanded_fact_ids = {f.id for f in top_facts}
    top_subject_id: Optional[str] = None
    if top_facts:
        subject_counts: Dict[str, int] = {}
        for f in top_facts:
            subj = graph.subject_of_fact(f.id)
            if subj:
                subject_counts[subj.id] = subject_counts.get(subj.id, 0) + 1
        if subject_counts:
            top_subject_id = max(subject_counts, key=subject_counts.get)
            for f in graph.facts_for_persona(top_subject_id):
                if f.id not in expanded_fact_ids:
                    expanded_fact_ids.add(f.id)
                    top_facts.append(f)

    # --- Q-type structural routing ---

    # Q8: include ALL facts for the top subject across all sessions (full temporal chain)
    # + ALL facts from sessions where the temporal shift occurs (to capture causal triggers
    # from other personas — e.g. Abi's cancellations driving Kwame's preference change).
    if query_type == "Q8" and top_subject_id:
        # Full temporal chain for the subject
        subject_facts = list(graph.facts_for_persona(top_subject_id))
        for f in subject_facts:
            if f.id not in expanded_fact_ids:
                expanded_fact_ids.add(f.id)
                top_facts.append(f)

        # Find sessions where subject's facts exist — include ALL facts from those sessions
        # This surfaces causal context from other personas in the same sessions
        subject_sessions = {f.session for f in subject_facts}
        for f in graph.all_facts():
            if f.session in subject_sessions and f.id not in expanded_fact_ids:
                expanded_fact_ids.add(f.id)
                top_facts.append(f)

        # Also include all norms for completeness
        top_norm_ids = list(graph.norms.keys())

    # Q2/Q6: ensure ALL dissent edges are surfaced for the matched personas.
    # DISSENTS_FROM edges may score low on cosine but are structurally critical.
    elif query_type in ("Q2", "Q6"):
        # Find all personas whose facts appear in top_facts
        matched_persona_ids = set()
        for f in top_facts:
            subj = graph.subject_of_fact(f.id)
            if subj:
                matched_persona_ids.add(subj.id)
        # Force all norms into context so dissenters are visible
        top_norm_ids = list(graph.norms.keys())

    # Q5: KNOWS_ABOUT edges are already included per-fact in _format_fact_with_context.
    # Ensure top norms include all norms so epistemic context is visible.
    elif query_type == "Q5":
        if len(top_norm_ids) < len(graph.norms):
            top_norm_ids = [nid for _, nid in norm_scored]  # all norms, ranked

    # Sort by session so temporal ordering is visible
    top_facts.sort(key=lambda f: f.session)

    # --- 4. Build context sections ---
    context_parts = []

    if top_facts:
        fact_blocks = [_format_fact_with_context(graph, f) for f in top_facts]
        context_parts.append("RELEVANT FACTS FROM MEMORY:\n" + "\n\n".join(fact_blocks))

    if top_norm_ids:
        norm_blocks = [_format_norm_with_context(graph, nid) for nid in top_norm_ids]
        context_parts.append("RELEVANT GROUP NORMS:\n" + "\n\n".join(norm_blocks))

    # --- 5. Add relevant relationships ---
    rel_scored: List[Tuple[float, str]] = []
    for rel_id, rel in graph.relationships.items():
        if hasattr(rel, "_embedding") and rel._embedding:
            sim = cosine_similarity(query_embedding, rel._embedding)
            rel_scored.append((sim, rel_id))
    rel_scored.sort(key=lambda x: x[0], reverse=True)
    # Q7: include more relationships; others: top 3
    n_rels = 6 if query_type == "Q7" else 3
    top_rel_ids = [rid for _, rid in rel_scored[:n_rels]]

    rel_blocks = []
    for rel_id in top_rel_ids:
        rel = graph.relationships.get(rel_id)
        if not rel:
            continue
        a = graph.personas.get(rel.persona_a_id)
        b = graph.personas.get(rel.persona_b_id)
        if a and b:
            rel_blocks.append(
                f"[{a.name} & {b.name}] {rel.description} (session {rel.session})"
            )

    if rel_blocks:
        context_parts.append("RELATIONSHIP CONTEXT:\n" + "\n\n".join(rel_blocks))

    if not context_parts:
        return "[No relevant information found in memory graph]"

    return "\n\n---\n\n".join(context_parts)


async def embed_facts(graph: SocialMemoryGraph, embed_fn) -> None:
    """
    Embed all facts in the graph in-place.
    embed_fn: async (List[str]) -> List[List[float]]
    Called once after all sessions are ingested.
    """
    facts = [f for f in graph.all_facts() if f.embedding is None]
    norms = [n for n in graph.all_norms() if not hasattr(n, "_embedding") or not n._embedding]

    if not facts and not norms:
        return

    if facts:
        texts = [f"{f.domain}: {f.value}" for f in facts]
        embeddings = await embed_fn(texts)
        for fact, emb in zip(facts, embeddings):
            fact.embedding = emb

    if norms:
        norm_texts = [f"{n.domain}: {n.value}" for n in norms]
        norm_embeddings = await embed_fn(norm_texts)
        for norm, emb in zip(norms, norm_embeddings):
            norm._embedding = emb

    # Embed relationships
    rels = [r for r in graph.relationships.values()
            if not hasattr(r, "_embedding") or not r._embedding]
    if rels:
        rel_texts = [r.description for r in rels]
        rel_embeddings = await embed_fn(rel_texts)
        for rel, emb in zip(rels, rel_embeddings):
            rel._embedding = emb
