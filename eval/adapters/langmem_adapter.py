"""
LangMem adapter for SocialMemBench evaluation.

LangMem (LangChain) uses a reflection + consolidation architecture:
after ingesting conversation episodes, an LLM consolidation pass merges,
deduplicates, and updates extracted memories — the closest analog to
human episodic-to-semantic consolidation.

Architectural distinction from other conditions:
  - naive_rag: stores raw turns verbatim (no extraction)
  - mem0_local: extraction → flat vector store (no consolidation)
  - graphiti: extraction → temporal knowledge graph
  - langmem: extraction + consolidation loop → managed memory store

The consolidation step makes LangMem uniquely suited to track preference
evolution (Q8) and resolve contradictions across sessions.

Requires Python >= 3.11 (smb311 conda env).
Install:
    pip install langmem langgraph

Configuration (eval/config/adapters/langmem.yaml):
    model: "gpt-4o-mini"
    embed_model: "text-embedding-3-small"
    top_k: 10
"""
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from eval.adapters.base import BaseAdapter
from eval.core.data_models import Dataset, AddResult, SearchResult
from eval.utils.logger import get_console, print_success


class LangMemAdapter(BaseAdapter):
    """
    LangMem adapter: reflection-based memory consolidation.

    Uses LangMem's create_memory_manager to run LLM-driven extraction +
    consolidation over each conversation session. Extracted memories are
    stored in LangGraph's InMemoryStore with vector indexing for semantic
    search. Memory is rebuilt fresh each run (ephemeral within-process store).
    """

    def __init__(self, config: Dict[str, Any], output_dir: Optional[Path] = None):
        super().__init__(config, output_dir)
        self.console = get_console()

        api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("LangMemAdapter requires OPENAI_API_KEY env var.")

        try:
            from langmem import create_memory_manager
            from langgraph.store.memory import InMemoryStore
        except ImportError:
            raise ImportError(
                "langmem and langgraph are required (Python >= 3.11).\n"
                "Install with: pip install langmem langgraph\n"
                "Use the smb311 conda environment."
            )

        self._model = config.get("model", "gpt-4o-mini")
        self._embed_model = config.get("embed_model", "text-embedding-3-small")
        self._top_k = config.get("top_k", 10)
        os.environ["OPENAI_API_KEY"] = api_key

        self._create_memory_manager = create_memory_manager
        self._InMemoryStore = InMemoryStore

        # Per-network state: network_id → {store, manager, all_memories, ingested}
        self._networks: Dict[str, Dict] = {}

        self.console.print("LangMemAdapter initialized", style="bold green")
        self.console.print(f"   Model: {self._model}")
        self.console.print(f"   Embed: {self._embed_model}")

    def _get_network(self, network_id: str) -> Dict:
        if network_id not in self._networks:
            store = self._InMemoryStore(
                index={
                    "dims": 1536,
                    "embed": f"openai:{self._embed_model}",
                }
            )
            manager = self._create_memory_manager(f"openai:{self._model}")
            self._networks[network_id] = {
                "store": store,
                "manager": manager,
                "all_memories": [],   # accumulated ExtractedMemory objects
                "ingested_sessions": set(),
            }
        return self._networks[network_id]

    async def add(
        self,
        dataset: Dataset,
        user_id: str,
        days_to_process: Optional[List[str]] = None,
        **kwargs,
    ) -> AddResult:
        """
        Ingest sessions via LangMem's memory manager.

        Each session is processed as a conversation. The manager extracts
        and consolidates memories relative to all previously seen memories,
        enabling cross-session updates (e.g. preference reversals for Q8).
        """
        self.console.print(f"\n{'='*60}", style="bold cyan")
        self.console.print("Stage: Add (LangMem)", style="bold cyan")
        self.console.print(f"{'='*60}", style="bold cyan")

        net = self._get_network(user_id)
        manager = net["manager"]
        store = net["store"]
        all_memories = net["all_memories"]
        ingested = net["ingested_sessions"]
        namespace = ("memories", user_id)

        days = [d for d in dataset.days if d.date in days_to_process] if days_to_process else dataset.days

        total_sent = 0
        errors = []

        for day in days:
            session_key = day.date
            if session_key in ingested:
                self.console.print(f"   Session {day.date} already ingested, skipping")
                continue

            session_idx = day.metadata.get("session_index", day.date)
            self.console.print(f"   Session {session_idx} ({day.date})...")

            for group_name, messages in day.groups.items():
                conv_messages = [
                    {"role": "user", "content": f"[{msg.speaker}] {msg.content}"}
                    for msg in messages
                ]

                try:
                    # Pass existing memories for consolidation (merge/update/delete)
                    result = await manager.ainvoke({
                        "messages": conv_messages,
                        "existing": [(m.id, m.content) for m in all_memories],
                    })

                    # result is a list of ExtractedMemory(id, content)
                    # Rebuild: apply deletes/updates, add inserts
                    result_ids = {m.id for m in result}
                    # Keep memories not returned (not modified); replace those returned
                    all_memories[:] = [m for m in all_memories if m.id not in result_ids]
                    all_memories.extend(result)

                    # Sync to store for vector search
                    for mem in result:
                        store.put(namespace, mem.id, {"content": mem.content})

                    total_sent += len(messages)
                except Exception as e:
                    errors.append(str(e))
                    self.console.print(f"   Session {session_idx} error: {e}", style="yellow")

            ingested.add(session_key)

        n_memories = len(all_memories)
        print_success(f"LangMem add: {total_sent} turns → {n_memories} consolidated memories, {len(errors)} errors")
        return AddResult(
            success=len(errors) == 0,
            days_processed=len(days),
            messages_sent=total_sent,
            errors=errors,
            metadata={"user_id": user_id, "n_memories": n_memories},
        )

    async def search(
        self,
        query: str,
        user_id: str,
        top_k: int = 10,
        **kwargs,
    ) -> SearchResult:
        """Search consolidated memories by vector similarity."""
        question_id = kwargs.get("question_id", "unknown")
        effective_k = top_k or self._top_k
        start = time.time()

        try:
            net = self._get_network(user_id)
            store = net["store"]
            namespace = ("memories", user_id)

            results = store.search(namespace, query=query, limit=effective_k)
            duration_ms = (time.time() - start) * 1000

            retrieved = []
            for item in results:
                content = item.value.get("content", str(item.value))
                retrieved.append(content)

            context = "\n".join(f"- {m}" for m in retrieved) if retrieved else "[No memories retrieved]"

        except Exception as e:
            self.console.print(f"   LangMem search error: {e}", style="yellow")
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
        self._networks.clear()
