"""
Graphiti adapter for SocialMemBench evaluation.

Uses Graphiti (Zep's open-source knowledge graph library) with an embedded
Kuzu graph database — no Docker, no external server required.

Graphiti builds a temporal knowledge graph from conversation episodes,
extracting entities and relationships via LLM. Search returns entity edges
(facts) ranked by relevance to the query.

Requires Python >= 3.10.

Install:
    pip install graphiti-core kuzu openai

Run in smb310 conda env:
    conda activate smb310
    python -m eval.cli --network grp_1a2b3c4d --condition graphiti

Configuration (eval/config/adapters/graphiti.yaml):
    model: "gpt-4o-mini"
    db_path: "./data/.graphiti_db"
    top_k: 10
"""
import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from eval.adapters.base import BaseAdapter
from eval.core.data_models import Dataset, AddResult, SearchResult
from eval.utils.logger import get_console, print_success


class GraphitiAdapter(BaseAdapter):
    """
    Graphiti knowledge graph adapter using embedded Kuzu storage.

    Each network gets its own Kuzu database on disk. Sessions are added
    as Graphiti episodes with the full turn text. Search returns entity
    edges (facts) most relevant to the query.
    """

    def __init__(self, config: Dict[str, Any], output_dir: Optional[Path] = None):
        super().__init__(config, output_dir)
        self.console = get_console()

        api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("GraphitiAdapter requires OPENAI_API_KEY env var.")

        try:
            from graphiti_core import Graphiti
            from graphiti_core.driver.kuzu_driver import KuzuDriver
            from graphiti_core.llm_client.openai_client import OpenAIClient
            from graphiti_core.llm_client.config import LLMConfig
            from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        except ImportError:
            raise ImportError(
                "graphiti-core and kuzu are required (Python >= 3.10).\n"
                "Install with: pip install graphiti-core kuzu\n"
                "Use the smb310 conda environment."
            )

        self._model = config.get("model", "gpt-4o-mini")
        self._top_k = config.get("top_k", 10)
        self._db_base = Path(config.get("db_path", "./data/.graphiti_db")).resolve()
        self._db_base.mkdir(parents=True, exist_ok=True)

        # Store imports for use in add/search
        self._Graphiti = Graphiti
        self._KuzuDriver = KuzuDriver
        self._OpenAIClient = OpenAIClient
        self._LLMConfig = LLMConfig
        self._OpenAIEmbedder = OpenAIEmbedder
        self._OpenAIEmbedderConfig = OpenAIEmbedderConfig
        self._api_key = api_key

        self._graphs: Dict[str, Any] = {}  # network_id → Graphiti instance

        self.console.print("✅ GraphitiAdapter initialized", style="bold green")
        self.console.print(f"   Model: {self._model}")
        self.console.print(f"   DB path: {self._db_base}")

    def _get_graph(self, network_id: str):
        """Get or create a Graphiti instance for this network."""
        if network_id not in self._graphs:
            db_path = str(self._db_base / network_id)
            driver = self._KuzuDriver(db=db_path)
            # KuzuDriver.__init__ doesn't set _database but graphiti.py:887 reads it
            # when group_id is passed to add_episode/search.  Set it to the network_id
            # so the identity check passes and the driver is not needlessly cloned.
            driver._database = network_id
            llm = self._OpenAIClient(
                config=self._LLMConfig(model=self._model, api_key=self._api_key)
            )
            embedder = self._OpenAIEmbedder(
                config=self._OpenAIEmbedderConfig(api_key=self._api_key)
            )
            self._graphs[network_id] = self._Graphiti(
                graph_driver=driver,
                llm_client=llm,
                embedder=embedder,
            )
        return self._graphs[network_id]

    async def _ensure_fts_indices(self, driver) -> None:
        """Create Kuzu FTS indices if they don't exist.

        graphiti-core 0.28.2's KuzuDriver.build_indices_and_constraints() is a
        no-op, so we create them directly.  The CREATE_FTS_INDEX call is
        idempotent in Kuzu 0.11+ (silently skipped if index already exists).
        """
        fts_queries = [
            "CALL CREATE_FTS_INDEX('Episodic', 'episode_content', ['content', 'source', 'source_description']);",
            "CALL CREATE_FTS_INDEX('Entity', 'node_name_and_summary', ['name', 'summary']);",
            "CALL CREATE_FTS_INDEX('Community', 'community_name', ['name']);",
            "CALL CREATE_FTS_INDEX('RelatesToNode_', 'edge_name_and_fact', ['name', 'fact']);",
        ]
        for q in fts_queries:
            try:
                await driver.execute_query(q)
            except Exception as e:
                err = str(e)
                # Ignore "already exists" errors
                if "already exist" in err.lower() or "already created" in err.lower():
                    pass
                else:
                    self.console.print(f"   ⚠️  FTS index warning: {err[:120]}", style="yellow")

    async def add(
        self,
        dataset: Dataset,
        user_id: str,
        days_to_process: Optional[List[str]] = None,
        **kwargs,
    ) -> AddResult:
        """
        Ingest conversation sessions as Graphiti episodes.

        Each session is added as a single episode (all turns concatenated)
        with the session date as reference_time. Graphiti extracts entities,
        relationships, and temporal facts automatically.
        """
        self.console.print(f"\n{'='*60}", style="bold cyan")
        self.console.print("Stage: Add (Graphiti)", style="bold cyan")
        self.console.print(f"{'='*60}", style="bold cyan")

        graph = self._get_graph(user_id)

        # Initialise schema + FTS indices on first use.
        # KuzuDriver.build_indices_and_constraints() is a no-op in graphiti-core
        # 0.28.2, so we create the FTS indexes directly via the driver.
        await self._ensure_fts_indices(graph.driver)

        days = [d for d in dataset.days if d.date in days_to_process] if days_to_process else dataset.days

        total_sent = 0
        errors = []

        for day in days:
            session_idx = day.metadata.get("session_index", day.date)
            self.console.print(f"   Session {session_idx} ({day.date})...")

            # Parse session date for reference_time
            try:
                ref_time = datetime.strptime(day.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                ref_time = datetime.now(timezone.utc)

            for group_name, messages in day.groups.items():
                # Concatenate all turns into one episode body
                lines = []
                for msg in messages:
                    lines.append(f"{msg.speaker}: {msg.content}")
                episode_body = "\n".join(lines)

                try:
                    await graph.add_episode(
                        name=f"{user_id}_session{session_idx}_{group_name}",
                        episode_body=episode_body,
                        source_description=f"Group chat session {session_idx} ({day.date})",
                        reference_time=ref_time,
                        group_id=user_id,
                    )
                    total_sent += len(messages)
                except Exception as e:
                    errors.append(str(e))
                    self.console.print(f"   ⚠️  Episode error: {e}", style="yellow")

        # Post-add verification: confirm graph has content
        try:
            test_edges = await graph.search(
                query="preferences",
                group_ids=[user_id],
                num_results=3,
            )
            n_edges = len(test_edges) if test_edges else 0
            self.console.print(f"   Graphiti verify: {n_edges} edges returned for test query")
            if n_edges == 0:
                self.console.print(
                    "   ⚠️  WARNING: 0 edges in graph after ingestion — "
                    "check graphiti version and group_ids API",
                    style="yellow",
                )
        except Exception as e:
            self.console.print(f"   ⚠️  Graphiti verify failed: {e}", style="yellow")

        print_success(f"Graphiti add: {total_sent} turns ingested, {len(errors)} errors")
        return AddResult(
            success=len(errors) == 0,
            days_processed=len(days),
            messages_sent=total_sent,
            errors=errors,
            metadata={"user_id": user_id},
        )

    async def search(
        self,
        query: str,
        user_id: str,
        top_k: int = 10,
        **kwargs,
    ) -> SearchResult:
        """Search the knowledge graph for facts relevant to the query."""
        question_id = kwargs.get("question_id", "unknown")
        effective_k = top_k or self._top_k
        start = time.time()

        search_error: Optional[str] = None
        try:
            graph = self._get_graph(user_id)
            edges = await graph.search(
                query=query,
                group_ids=[user_id],
                num_results=effective_k,
            )
            duration_ms = (time.time() - start) * 1000

            retrieved = []
            for edge in edges:
                fact = getattr(edge, "fact", None) or str(edge)
                retrieved.append(fact)

            context = "\n".join(f"- {f}" for f in retrieved) if retrieved else "[No facts retrieved]"

        except Exception as e:
            search_error = str(e)
            self.console.print(
                f"   ⚠️  Graphiti search error ({type(e).__name__}): {e}",
                style="yellow",
            )
            duration_ms = (time.time() - start) * 1000
            retrieved = []
            context = f"[Search failed: {type(e).__name__}: {str(e)[:120]}]"

        return SearchResult(
            question_id=question_id,
            query=query,
            retrieved_memories=retrieved,
            context=context,
            search_duration_ms=duration_ms,
            metadata={
                "user_id": user_id,
                "top_k": effective_k,
                "search_error": search_error,
            },
        )

    async def close(self):
        for graph in self._graphs.values():
            try:
                await graph.close()
            except Exception:
                pass
        self._graphs.clear()
