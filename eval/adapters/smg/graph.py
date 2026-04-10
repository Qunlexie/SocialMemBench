"""
Social Memory Graph — core data model and graph operations.

The SocialMemoryGraph is a person-attributed knowledge graph for social group
memory. Its central design principle: person identity is a structural graph node,
not a text field. Every fact is anchored to the person who holds it via a typed
edge, set from the source data (speaker_display_name) before any LLM runs.

This separates SMG from every other memory system:
  - naive_rag: person identity is a text prefix, matched lexically
  - mem0/graphiti/cognee/langmem: person identity is inferred by LLM (lossy)
  - SMG: person identity is a graph node (structural, always correct)

The graph is persisted as JSON on disk (one file per network). Vector embeddings
for fact content are stored separately (see queries.py) for semantic search.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Node dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Persona:
    """A group member. Primary anchor for all facts in the graph."""
    id: str               # persona_id from source data (e.g. "p_abc123")
    name: str             # display_name (e.g. "Marcus")
    group_id: str         # which network this person belongs to


@dataclass
class Fact:
    """
    One extracted belief, preference, or state about a person.

    The subject of a fact is always a Persona node (linked via HOLDS edge).
    The speaker may be the same persona (self-disclosed) or different (third-party).
    implicitness mirrors the benchmark's scale: 1=explicit, 2=implied, 3=silence/deflection.
    """
    id: str
    domain: str           # short label, e.g. "trail_difficulty"
    value: str            # the belief, e.g. "dislikes steep trails"
    session: int          # session index when this was observed
    implicitness: int     # 1 | 2 | 3
    evidence_quote: str   # exact excerpt from the source turn (≤120 chars)
    embedding: Optional[List[float]] = None  # set after embedding; not serialized to graph JSON


@dataclass
class GroupNorm:
    """A norm stated as applying to the whole group."""
    id: str
    domain: str
    value: str            # e.g. "the group always meets on Saturdays"
    session: int
    truly_universal: bool = True  # set to False when any DISSENTS_FROM edge is added


@dataclass
class Relationship:
    """Dyadic relationship state between two personas at a given session."""
    id: str
    persona_a_id: str
    persona_b_id: str
    description: str      # e.g. "childhood friends who met at university"
    session: int


# ---------------------------------------------------------------------------
# Edge dataclasses
# ---------------------------------------------------------------------------

@dataclass
class HoldsEdge:
    """Persona holds/is-subject-of a Fact. Primary attribution edge."""
    persona_id: str
    fact_id: str
    session: int


@dataclass
class StatedEdge:
    """Persona stated/expressed a Fact (may be about themselves or another)."""
    persona_id: str
    fact_id: str
    session: int
    turn_idx: int


@dataclass
class KnowsAboutEdge:
    """Persona demonstrated in-conversation awareness of another's Fact."""
    persona_id: str       # the knower
    fact_id: str          # the fact they know about (subject is another persona)
    session: int
    evidence: str         # what in the conversation showed they knew


@dataclass
class EvolvedFromEdge:
    """A Fact supersedes an older Fact (temporal versioning)."""
    new_fact_id: str
    old_fact_id: str
    session: int          # session where the shift was observed
    trigger: str          # brief description of what caused the change


@dataclass
class DissentsFromEdge:
    """Persona implicitly or explicitly rejected a GroupNorm."""
    persona_id: str
    norm_id: str
    session: int
    signal: str           # "explicit_reject" | "qualifier" | "silence" | "topic_change"


@dataclass
class EndorsesEdge:
    """Persona agreed with or accepted a GroupNorm."""
    persona_id: str
    norm_id: str
    session: int


@dataclass
class RelatedToEdge:
    """Dyadic relationship link between two personas."""
    persona_a_id: str
    persona_b_id: str
    relationship_id: str


# ---------------------------------------------------------------------------
# Social Memory Graph
# ---------------------------------------------------------------------------

class SocialMemoryGraph:
    """
    Person-attributed knowledge graph for social group memory.

    All nodes and edges are stored in plain Python dicts indexed by ID.
    The graph is serialized to / loaded from a JSON file on disk for
    persistence across eval runs.

    Indexing model:
      - Structural queries (Q1, Q2, Q3, Q5, Q6, Q7, Q8) use graph traversal
      - Semantic search (Q4) uses a separate vector index (see queries.py)
        over Fact.value embeddings, returning persona via HOLDS edges
    """

    def __init__(self, group_id: str):
        self.group_id = group_id

        # Nodes
        self.personas: Dict[str, Persona] = {}         # id → Persona
        self.facts: Dict[str, Fact] = {}               # id → Fact
        self.norms: Dict[str, GroupNorm] = {}          # id → GroupNorm
        self.relationships: Dict[str, Relationship] = {}  # id → Relationship

        # Edges (stored as lists, indexed by source node for fast lookup)
        self.holds: List[HoldsEdge] = []               # persona → fact (subject)
        self.stated: List[StatedEdge] = []             # persona → fact (speaker)
        self.knows_about: List[KnowsAboutEdge] = []   # persona → fact (knower)
        self.evolved_from: List[EvolvedFromEdge] = []  # new_fact → old_fact
        self.dissents_from: List[DissentsFromEdge] = []
        self.endorses: List[EndorsesEdge] = []
        self.related_to: List[RelatedToEdge] = []

    # ------------------------------------------------------------------
    # Node creation helpers
    # ------------------------------------------------------------------

    def get_or_create_persona(self, persona_id: str, name: str) -> Persona:
        """Return existing persona or create new one. Never requires LLM."""
        if persona_id not in self.personas:
            self.personas[persona_id] = Persona(
                id=persona_id, name=name, group_id=self.group_id
            )
        return self.personas[persona_id]

    def add_fact(
        self,
        subject_id: str,
        speaker_id: str,
        domain: str,
        value: str,
        session: int,
        implicitness: int,
        evidence_quote: str,
        turn_idx: int = 0,
    ) -> Fact:
        """
        Add a Fact node with HOLDS (subject) and STATED (speaker) edges.
        If a fact already exists for (subject, domain) from an earlier session,
        add an EVOLVED_FROM edge automatically.
        """
        fact_id = f"f_{uuid.uuid4().hex[:8]}"
        fact = Fact(
            id=fact_id,
            domain=domain,
            value=value,
            session=session,
            implicitness=implicitness,
            evidence_quote=evidence_quote[:120],
        )
        self.facts[fact_id] = fact

        # HOLDS edge: subject persona holds this fact
        self.holds.append(HoldsEdge(
            persona_id=subject_id, fact_id=fact_id, session=session
        ))

        # STATED edge: speaker stated this fact
        self.stated.append(StatedEdge(
            persona_id=speaker_id, fact_id=fact_id, session=session, turn_idx=turn_idx
        ))

        # EVOLVED_FROM: if a prior fact exists for same (subject, domain), link it
        prior = self._find_prior_fact(subject_id, domain, before_session=session)
        if prior:
            self.evolved_from.append(EvolvedFromEdge(
                new_fact_id=fact_id,
                old_fact_id=prior.id,
                session=session,
                trigger="preference_update",
            ))

        return fact

    def add_knows_about(
        self, knower_id: str, fact_id: str, session: int, evidence: str
    ) -> None:
        self.knows_about.append(KnowsAboutEdge(
            persona_id=knower_id, fact_id=fact_id, session=session, evidence=evidence
        ))

    def add_norm(
        self, domain: str, value: str, session: int, speaker_id: str
    ) -> GroupNorm:
        # Check if a matching norm already exists for this domain
        for norm in self.norms.values():
            if norm.domain == domain:
                self.endorses.append(EndorsesEdge(
                    persona_id=speaker_id, norm_id=norm.id, session=session
                ))
                return norm

        norm_id = f"n_{uuid.uuid4().hex[:8]}"
        norm = GroupNorm(id=norm_id, domain=domain, value=value, session=session)
        self.norms[norm_id] = norm
        self.endorses.append(EndorsesEdge(
            persona_id=speaker_id, norm_id=norm_id, session=session
        ))
        return norm

    def add_dissent(
        self, persona_id: str, norm_id: str, session: int, signal: str
    ) -> None:
        self.dissents_from.append(DissentsFromEdge(
            persona_id=persona_id, norm_id=norm_id, session=session, signal=signal
        ))
        if norm_id in self.norms:
            self.norms[norm_id].truly_universal = False

    def add_relationship(
        self,
        persona_a_id: str,
        persona_b_id: str,
        description: str,
        session: int,
    ) -> Relationship:
        # Canonical key: sort IDs so A↔B and B↔A are the same relationship
        key = tuple(sorted([persona_a_id, persona_b_id]))
        existing = next(
            (r for r in self.relationships.values()
             if tuple(sorted([r.persona_a_id, r.persona_b_id])) == key),
            None
        )
        if existing:
            existing.description = description  # update with latest
            existing.session = session
            return existing

        rel_id = f"r_{uuid.uuid4().hex[:8]}"
        rel = Relationship(
            id=rel_id,
            persona_a_id=persona_a_id,
            persona_b_id=persona_b_id,
            description=description,
            session=session,
        )
        self.relationships[rel_id] = rel
        self.related_to.append(RelatedToEdge(
            persona_a_id=persona_a_id,
            persona_b_id=persona_b_id,
            relationship_id=rel_id,
        ))
        return rel

    # ------------------------------------------------------------------
    # Structural query helpers (used by queries.py)
    # ------------------------------------------------------------------

    def facts_for_persona(self, persona_id: str) -> List[Fact]:
        """All facts held by this persona (via HOLDS edges)."""
        fact_ids = {e.fact_id for e in self.holds if e.persona_id == persona_id}
        return [self.facts[fid] for fid in fact_ids if fid in self.facts]

    def facts_stated_by_persona(self, persona_id: str) -> List[Fact]:
        """All facts this persona stated (via STATED edges)."""
        fact_ids = {e.fact_id for e in self.stated if e.persona_id == persona_id}
        return [self.facts[fid] for fid in fact_ids if fid in self.facts]

    def subject_of_fact(self, fact_id: str) -> Optional[Persona]:
        """Return the persona who HOLDS this fact (the subject)."""
        edge = next((e for e in self.holds if e.fact_id == fact_id), None)
        if edge:
            return self.personas.get(edge.persona_id)
        return None

    def speaker_of_fact(self, fact_id: str) -> Optional[Persona]:
        """Return the persona who STATED this fact (the speaker)."""
        edge = next((e for e in self.stated if e.fact_id == fact_id), None)
        if edge:
            return self.personas.get(edge.persona_id)
        return None

    def knowers_of_fact(self, fact_id: str) -> List[Tuple[Persona, str]]:
        """Return (persona, evidence) for all personas who KNOW_ABOUT this fact."""
        result = []
        for e in self.knows_about:
            if e.fact_id == fact_id and e.persona_id in self.personas:
                result.append((self.personas[e.persona_id], e.evidence))
        return result

    def temporal_chain(self, fact_id: str) -> List[Fact]:
        """
        Follow EVOLVED_FROM edges backward from fact_id to get the full
        temporal chain, oldest first.
        """
        chain = []
        current_id = fact_id
        seen = set()
        while current_id and current_id not in seen:
            seen.add(current_id)
            if current_id in self.facts:
                chain.append(self.facts[current_id])
            prev = next(
                (e.old_fact_id for e in self.evolved_from if e.new_fact_id == current_id),
                None
            )
            current_id = prev
        chain.reverse()  # oldest → newest
        return chain

    def dissenters_of_norm(self, norm_id: str) -> List[Tuple[Persona, str]]:
        """Return (persona, signal) for all dissenters of a norm."""
        result = []
        for e in self.dissents_from:
            if e.norm_id == norm_id and e.persona_id in self.personas:
                result.append((self.personas[e.persona_id], e.signal))
        return result

    def relationship_between(
        self, persona_a_id: str, persona_b_id: str
    ) -> Optional[Relationship]:
        key = tuple(sorted([persona_a_id, persona_b_id]))
        for r in self.relationships.values():
            if tuple(sorted([r.persona_a_id, r.persona_b_id])) == key:
                return r
        return None

    def all_personas(self) -> List[Persona]:
        return list(self.personas.values())

    def all_facts(self) -> List[Fact]:
        return list(self.facts.values())

    def all_norms(self) -> List[GroupNorm]:
        return list(self.norms.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_prior_fact(
        self, persona_id: str, domain: str, before_session: int
    ) -> Optional[Fact]:
        """Find the most recent fact for (persona, domain) before the given session."""
        held_ids = {e.fact_id for e in self.holds if e.persona_id == persona_id}
        candidates = [
            f for fid, f in self.facts.items()
            if fid in held_ids and f.domain == domain and f.session < before_session
        ]
        return max(candidates, key=lambda f: f.session) if candidates else None

    def persona_by_name(self, name: str) -> Optional[Persona]:
        """Case-insensitive name lookup."""
        name_lower = name.lower()
        for p in self.personas.values():
            if p.name.lower() == name_lower:
                return p
        return None

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize the full graph to a JSON-compatible dict."""
        def _list(items):
            return [asdict(x) for x in items]

        return {
            "group_id": self.group_id,
            "personas": {k: asdict(v) for k, v in self.personas.items()},
            "facts": {
                k: {f: val for f, val in asdict(v).items() if f != "embedding"}
                for k, v in self.facts.items()
            },
            "norms": {k: asdict(v) for k, v in self.norms.items()},
            "relationships": {k: asdict(v) for k, v in self.relationships.items()},
            "holds": _list(self.holds),
            "stated": _list(self.stated),
            "knows_about": _list(self.knows_about),
            "evolved_from": _list(self.evolved_from),
            "dissents_from": _list(self.dissents_from),
            "endorses": _list(self.endorses),
            "related_to": _list(self.related_to),
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "SocialMemoryGraph":
        with open(path) as f:
            data = json.load(f)
        g = cls(group_id=data["group_id"])
        g.personas = {k: Persona(**v) for k, v in data["personas"].items()}
        g.facts = {k: Fact(**v) for k, v in data["facts"].items()}
        g.norms = {k: GroupNorm(**v) for k, v in data["norms"].items()}
        g.relationships = {k: Relationship(**v) for k, v in data["relationships"].items()}
        g.holds = [HoldsEdge(**e) for e in data["holds"]]
        g.stated = [StatedEdge(**e) for e in data["stated"]]
        g.knows_about = [KnowsAboutEdge(**e) for e in data["knows_about"]]
        g.evolved_from = [EvolvedFromEdge(**e) for e in data["evolved_from"]]
        g.dissents_from = [DissentsFromEdge(**e) for e in data["dissents_from"]]
        g.endorses = [EndorsesEdge(**e) for e in data["endorses"]]
        g.related_to = [RelatedToEdge(**e) for e in data["related_to"]]
        return g
