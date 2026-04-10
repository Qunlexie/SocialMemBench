"""
Cognee adapter for SocialMemBench evaluation.

Cognee builds a knowledge graph from conversation text via a multi-stage
LLM pipeline: classify → chunk → entity/relationship extraction → summarize
→ embed + graph commit. Retrieval uses hybrid vector-hint → graph traversal.

Architectural distinction:
  - graphiti: streaming, turn-by-turn, temporal edges, episode-based ingestion
  - cognee: batch document-level processing, static ontology extraction,
            summary nodes, memify() for adaptive graph maintenance

Requires Python >= 3.10, smb310 conda env.
Install:
    pip install cognee

Configuration (eval/config/adapters/cognee.yaml):
    model: "gpt-4o-mini"
    embed_model: "text-embedding-3-small"
    db_path: "./data/.cognee_db"
    top_k: 10
"""
import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from eval.adapters.base import BaseAdapter
from eval.core.data_models import Dataset, AddResult, SearchResult
from eval.utils.logger import get_console, print_success


class CogneeAdapter(BaseAdapter):
    """
    Cognee adapter: batch document-to-knowledge-graph with hybrid retrieval.

    Each network's sessions are concatenated into a corpus and processed
    through cognee's cognify() pipeline. A separate cognee data directory
    is used per network for isolation.
    """

    def __init__(self, config: Dict[str, Any], output_dir: Optional[Path] = None):
        super().__init__(config, output_dir)
        self.console = get_console()

        api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("CogneeAdapter requires OPENAI_API_KEY env var.")

        try:
            import cognee
        except ImportError:
            raise ImportError(
                "cognee is required (Python >= 3.10).\n"
                "Install with: pip install cognee\n"
                "Use the smb310 conda environment."
            )

        self._model = config.get("model", "gpt-4o-mini")
        self._embed_model = config.get("embed_model", "text-embedding-3-small")
        self._top_k = config.get("top_k", 10)
        self._db_base = Path(config.get("db_path", "./data/.cognee_db")).resolve()
        self._db_base.mkdir(parents=True, exist_ok=True)
        self._api_key = api_key

        self._cognee = cognee
        self._ingested: set = set()  # network_ids already cognified

        self.console.print("CogneeAdapter initialized", style="bold green")
        self.console.print(f"   Model: {self._model}")
        self.console.print(f"   DB path: {self._db_base}")

    def _configure_for_network(self, network_id: str):
        """Point cognee at a per-network data directory."""
        db_path = str(self._db_base / network_id)
        Path(db_path).mkdir(parents=True, exist_ok=True)

        self._cognee.config.set_llm_api_key(self._api_key)
        self._cognee.config.set_llm_model(self._model)
        self._cognee.config.set_llm_provider("openai")

        self._cognee.config.set_embedding_api_key(self._api_key)
        self._cognee.config.set_embedding_model(self._embed_model)
        self._cognee.config.set_embedding_provider("openai")

        # Point data dirs at per-network path
        os.environ["COGNEE_DB_PATH"] = db_path
        os.environ["COGNEE_DATA_ROOT_PATH"] = db_path

    async def add(
        self,
        dataset: Dataset,
        user_id: str,
        days_to_process: Optional[List[str]] = None,
        **kwargs,
    ) -> AddResult:
        """
        Ingest conversation corpus via cognee's cognify() pipeline.

        All sessions are concatenated into a single corpus document and
        processed together (cognee is batch-oriented, not streaming).
        Re-ingestion is skipped if network was already cognified this run.
        """
        self.console.print(f"\n{'='*60}", style="bold cyan")
        self.console.print("Stage: Add (Cognee)", style="bold cyan")
        self.console.print(f"{'='*60}", style="bold cyan")

        if user_id in self._ingested:
            self.console.print(f"   {user_id} already cognified this run, skipping")
            total_turns = sum(
                len(msgs)
                for day in dataset.days
                for msgs in day.groups.values()
            )
            return AddResult(
                success=True,
                days_processed=0,
                messages_sent=total_turns,
                errors=[],
                metadata={"user_id": user_id, "skipped": True},
            )

        self._configure_for_network(user_id)
        days = [d for d in dataset.days if d.date in days_to_process] if days_to_process else dataset.days

        # Build full corpus as one text document
        corpus_lines = []
        total_sent = 0
        for day in days:
            session_idx = day.metadata.get("session_index", day.date)
            corpus_lines.append(f"\n--- Session {session_idx} ({day.date}) ---")
            for group_name, messages in day.groups.items():
                for msg in messages:
                    corpus_lines.append(f"[{msg.speaker}] {msg.content}")
                    total_sent += 1

        corpus_text = "\n".join(corpus_lines)

        errors = []
        try:
            self.console.print("   Resetting cognee state for network...")
            await self._cognee.prune.prune_data()
            await self._cognee.prune.prune_system(metadata=True)

            self.console.print(f"   Adding corpus ({total_sent} turns)...")
            await self._cognee.add(corpus_text)

            self.console.print("   Running cognify() — LLM extraction pipeline...")
            await self._cognee.cognify()

            self._ingested.add(user_id)
        except Exception as e:
            errors.append(str(e))
            self.console.print(f"   Cognee add/cognify error: {e}", style="red")

        print_success(f"Cognee add: {total_sent} turns cognified, {len(errors)} errors")
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
        """Search the knowledge graph for relevant facts."""
        question_id = kwargs.get("question_id", "unknown")
        start = time.time()

        try:
            self._configure_for_network(user_id)
            results = await self._cognee.search(query)
            duration_ms = (time.time() - start) * 1000

            retrieved = []
            for r in results:
                if isinstance(r, str):
                    retrieved.append(r)
                elif hasattr(r, "text"):
                    retrieved.append(r.text)
                elif hasattr(r, "content"):
                    retrieved.append(r.content)
                else:
                    retrieved.append(str(r))
                if len(retrieved) >= (top_k or self._top_k):
                    break

            context = "\n".join(f"- {m}" for m in retrieved) if retrieved else "[No results retrieved]"

        except Exception as e:
            self.console.print(f"   Cognee search error: {e}", style="yellow")
            duration_ms = (time.time() - start) * 1000
            retrieved = []
            context = "[Search failed]"

        return SearchResult(
            question_id=question_id,
            query=query,
            retrieved_memories=retrieved,
            context=context,
            search_duration_ms=duration_ms,
            metadata={"user_id": user_id, "top_k": top_k or self._top_k},
        )

    async def close(self):
        self._ingested.clear()
