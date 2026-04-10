"""
SMG (Social Memory Graph) adapter for SocialMemBench evaluation.

Two-stage pipeline:
  Stage 1 — add(): build graph from conversations (no QA knowledge)
  Stage 2 — search(): retrieve context from graph (no Q-type knowledge)

The graph is persisted to disk between runs. If a network's graph already
exists on disk, add() skips re-ingestion (incremental, same pattern as
naive_rag's Chroma check).
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from eval.adapters.base import BaseAdapter
from eval.adapters.smg.graph import SocialMemoryGraph
from eval.adapters.smg.extractor import extract_session
from eval.adapters.smg.queries import retrieve_context, embed_facts
from eval.core.data_models import Dataset, AddResult, SearchResult
from eval.utils.logger import get_console, print_success


class SMGAdapter(BaseAdapter):
    """
    Social Memory Graph adapter.

    Builds a person-attributed knowledge graph from conversation sessions.
    All facts are structurally linked to the person who holds them — set
    from source data, never inferred by LLM.

    Search returns structured graph context (subject, speaker, knowers,
    temporal chain, group norms + dissenters) without any Q-type routing.
    """

    def __init__(self, config: Dict[str, Any], output_dir: Optional[Path] = None):
        super().__init__(config, output_dir)
        self.console = get_console()

        api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("SMGAdapter requires OPENAI_API_KEY env var.")

        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("Install with: pip install openai")

        self._llm = AsyncOpenAI(api_key=api_key)
        self._embed_model = config.get("embed_model", "text-embedding-3-small")
        self._top_k = config.get("top_k", 10)
        self._graph_dir = Path(config.get("graph_dir", "./data/.smg_graphs")).resolve()
        self._graph_dir.mkdir(parents=True, exist_ok=True)

        # In-memory graphs for this run: network_id → SocialMemoryGraph
        self._graphs: Dict[str, SocialMemoryGraph] = {}

        self.console.print("SMGAdapter initialized", style="bold green")
        self.console.print(f"   Graph dir: {self._graph_dir}")

    # ------------------------------------------------------------------
    # Embedding helper
    # ------------------------------------------------------------------

    async def _embed_async(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        # Batch in chunks of 100
        all_embeddings = []
        for i in range(0, len(texts), 100):
            batch = texts[i:i + 100]
            resp = await self._llm.embeddings.create(
                model=self._embed_model, input=batch
            )
            all_embeddings.extend([r.embedding for r in resp.data])
        return all_embeddings

    # ------------------------------------------------------------------
    # Graph load/get
    # ------------------------------------------------------------------

    def _graph_path(self, network_id: str) -> Path:
        return self._graph_dir / f"{network_id}.json"

    def _get_or_load_graph(self, network_id: str) -> SocialMemoryGraph:
        if network_id not in self._graphs:
            path = self._graph_path(network_id)
            if path.exists():
                self._graphs[network_id] = SocialMemoryGraph.load(path)
            else:
                self._graphs[network_id] = SocialMemoryGraph(group_id=network_id)
        return self._graphs[network_id]

    # ------------------------------------------------------------------
    # add(): build graph from conversations
    # ------------------------------------------------------------------

    async def add(
        self,
        dataset: Dataset,
        user_id: str,
        days_to_process: Optional[List[str]] = None,
        **kwargs,
    ) -> AddResult:
        self.console.print(f"\n{'='*60}", style="bold cyan")
        self.console.print("Stage: Add (SMG)", style="bold cyan")
        self.console.print(f"{'='*60}", style="bold cyan")

        graph = self._get_or_load_graph(user_id)

        # Get all persona names from the dataset for the extraction prompt
        member_names = sorted({
            msg.speaker
            for day in dataset.days
            for msgs in day.groups.values()
            for msg in msgs
        })

        days = (
            [d for d in dataset.days if d.date in days_to_process]
            if days_to_process else dataset.days
        )

        total_turns = 0
        total_facts = 0
        errors = []

        for day in days:
            session_idx = day.metadata.get("session_index", 1)
            if isinstance(session_idx, str):
                try:
                    session_idx = int(session_idx)
                except ValueError:
                    session_idx = 1

            # Skip if this session already ingested (check for any fact at this session)
            already_ingested = any(
                f.session == session_idx for f in graph.all_facts()
            )
            if already_ingested:
                self.console.print(
                    f"   Session {session_idx} already in graph, skipping"
                )
                continue

            self.console.print(f"   Session {session_idx} ({day.date})...")

            for group_name, messages in day.groups.items():
                # Build turn list — speaker_id comes from source data (not LLM)
                turns = [
                    {
                        "speaker": msg.speaker,
                        "speaker_id": getattr(msg, "speaker_id", msg.speaker),
                        "message": msg.content,
                    }
                    for msg in messages
                ]
                total_turns += len(turns)

                # Build prior-facts summary for temporal shift detection
                # This only passes what the graph already knows — no QA data
                prior_facts = None
                if session_idx > 1:
                    prior_facts = [
                        {
                            "subject": graph.subject_of_fact(f.id).name
                            if graph.subject_of_fact(f.id) else "unknown",
                            "domain": f.domain,
                            "value": f.value,
                            "session": f.session,
                        }
                        for f in graph.all_facts()
                        if f.session < session_idx
                    ]

                try:
                    signals = await extract_session(
                        self._llm, turns, member_names, session_idx,
                        prior_facts=prior_facts,
                    )
                    n_inserted = self._insert_signals(
                        graph, signals, turns, member_names, session_idx
                    )
                    total_facts += n_inserted
                    self.console.print(
                        f"     → {n_inserted} facts extracted"
                    )
                except Exception as e:
                    errors.append(str(e))
                    self.console.print(f"   ⚠ Session {session_idx}: {e}", style="yellow")

        # Embed all facts that don't have embeddings yet
        self.console.print("   Embedding facts...")
        try:
            await embed_facts(graph, self._embed_async)
        except Exception as e:
            errors.append(f"Embedding error: {e}")
            self.console.print(f"   ⚠ Embedding failed: {e}", style="yellow")

        # Persist graph to disk
        graph.save(self._graph_path(user_id))

        n_facts = len(graph.all_facts())
        n_norms = len(graph.all_norms())
        n_personas = len(graph.all_personas())
        print_success(
            f"SMG: {n_personas} personas, {n_facts} facts, {n_norms} norms, "
            f"{len(graph.knows_about)} epistemic edges, "
            f"{len(graph.evolved_from)} temporal chains"
        )

        return AddResult(
            success=len(errors) == 0,
            days_processed=len(days),
            messages_sent=total_turns,
            errors=errors,
            metadata={
                "user_id": user_id,
                "n_personas": n_personas,
                "n_facts": n_facts,
                "n_norms": n_norms,
                "n_epistemic_edges": len(graph.knows_about),
                "n_temporal_chains": len(graph.evolved_from),
            },
        )

    def _insert_signals(
        self,
        graph: SocialMemoryGraph,
        signals: Dict[str, List],
        turns: List[Dict],
        member_names: List[str],
        session: int,
    ) -> int:
        """Insert extracted signals into the graph. Returns number of facts inserted."""
        member_set = {n.lower() for n in member_names}
        inserted = 0

        # Ensure all speakers in this session have Persona nodes
        for turn in turns:
            graph.get_or_create_persona(
                persona_id=turn["speaker_id"],
                name=turn["speaker"],
            )

        # Insert facts
        for f in signals.get("facts", []):
            subject_name = f.get("subject", "")
            speaker_name = f.get("speaker", "")

            if subject_name.lower() not in member_set:
                continue  # reject hallucinated subjects
            if speaker_name.lower() not in member_set:
                continue  # reject hallucinated speakers

            subject = graph.persona_by_name(subject_name)
            speaker = graph.persona_by_name(speaker_name)
            if not subject or not speaker:
                continue

            graph.add_fact(
                subject_id=subject.id,
                speaker_id=speaker.id,
                domain=f.get("domain", "general"),
                value=f.get("value", ""),
                session=session,
                implicitness=int(f.get("implicitness", 2)),
                evidence_quote=f.get("evidence_quote", ""),
            )
            inserted += 1

        # Insert epistemic signals (knows_about)
        for k in signals.get("knows_about", []):
            knower = graph.persona_by_name(k.get("knower", ""))
            subject = graph.persona_by_name(k.get("subject", ""))
            if not knower or not subject:
                continue
            # Find the most recent fact for this (subject, domain)
            domain = k.get("domain", "")
            subject_facts = [
                f for f in graph.facts_for_persona(subject.id)
                if f.domain == domain
            ]
            if subject_facts:
                most_recent = max(subject_facts, key=lambda f: f.session)
                graph.add_knows_about(
                    knower_id=knower.id,
                    fact_id=most_recent.id,
                    session=session,
                    evidence=k.get("evidence_quote", ""),
                )

        # Insert group norms
        for n in signals.get("norms", []):
            speaker = graph.persona_by_name(n.get("speaker", ""))
            if not speaker:
                continue
            graph.add_norm(
                domain=n.get("domain", "general"),
                value=n.get("value", ""),
                session=session,
                speaker_id=speaker.id,
            )

        # Insert dissent signals
        for d in signals.get("dissents", []):
            speaker = graph.persona_by_name(d.get("speaker", ""))
            if not speaker:
                continue
            norm_domain = d.get("norm_domain", "")
            # Find matching norm by domain
            matching_norms = [
                nid for nid, n in graph.norms.items()
                if n.domain == norm_domain
            ]
            for norm_id in matching_norms:
                graph.add_dissent(
                    persona_id=speaker.id,
                    norm_id=norm_id,
                    session=session,
                    signal=d.get("signal", "qualifier"),
                )

        # Insert relationship signals
        for r in signals.get("relationships", []):
            a = graph.persona_by_name(r.get("persona_a", ""))
            b = graph.persona_by_name(r.get("persona_b", ""))
            if not a or not b:
                continue
            graph.add_relationship(
                persona_a_id=a.id,
                persona_b_id=b.id,
                description=r.get("description", ""),
                session=session,
            )

        return inserted

    # ------------------------------------------------------------------
    # search(): retrieve context from graph
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        user_id: str,
        top_k: int = 10,
        **kwargs,
    ) -> SearchResult:
        question_id = kwargs.get("question_id", "unknown")
        effective_k = top_k or self._top_k
        start = time.time()

        try:
            graph = self._get_or_load_graph(user_id)

            # Embed the question
            q_emb = await self._embed_async([query])
            query_embedding = q_emb[0]

            # Retrieve context — no Q-type routing, pure semantic + structural
            context = retrieve_context(graph, query_embedding, top_k=effective_k)
            duration_ms = (time.time() - start) * 1000

            # Extract retrieved fact values for metadata
            retrieved = [
                f"{f.domain}: {f.value}"
                for f in graph.all_facts()
                if f.embedding
            ][:effective_k]

        except Exception as e:
            self.console.print(f"   ⚠ SMG search error: {e}", style="yellow")
            duration_ms = (time.time() - start) * 1000
            retrieved = []
            context = "[Search failed]"

        return SearchResult(
            question_id=question_id,
            query=query,
            retrieved_memories=retrieved,
            context=context,
            search_duration_ms=duration_ms,
            metadata={"user_id": user_id, "top_k": effective_k},
        )

    async def close(self):
        self._graphs.clear()
