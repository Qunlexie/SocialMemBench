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
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from eval.adapters.base import BaseAdapter
from eval.core.data_models import Dataset, AddResult, SearchResult
from eval.utils.logger import get_console, print_success


@dataclass
class _MemoryItem:
    """
    Rehydrated memory loaded from disk. Duck-types langmem's ExtractedMemory:
    the only attributes we consume are `.id` and `.content` (see uses in
    `manager.ainvoke({"existing": ...})` and `store.put`).
    """
    id: str
    content: str


class LangMemAdapter(BaseAdapter):
    """
    LangMem adapter: reflection-based memory consolidation.

    Uses LangMem's create_memory_manager to run LLM-driven extraction +
    consolidation over each conversation session. Extracted memories are
    stored in LangGraph's InMemoryStore with vector indexing for semantic
    search. After add() completes, the consolidated memories and the set of
    ingested session dates are serialized to disk (see _save_network); on a
    fresh process, _get_network() reads that file and re-populates a new
    InMemoryStore so search() works without re-ingest.
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

        self._persist_dir = Path(config.get("persist_dir", "./data/.langmem")).resolve()
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        # Per-network state: network_id → {store, manager, all_memories, ingested}
        self._networks: Dict[str, Dict] = {}

        self.console.print("LangMemAdapter initialized", style="bold green")
        self.console.print(f"   Model: {self._model}")
        self.console.print(f"   Embed: {self._embed_model}")

    def _persist_path(self, network_id: str) -> Path:
        return self._persist_dir / f"{network_id}.json"

    def _save_network(self, network_id: str, net: Dict) -> None:
        """
        Serialize consolidated memories + ingested-session dates.
        The InMemoryStore itself isn't serialized: on load we re-populate it
        by calling store.put() for each memory, which re-embeds via the
        configured OpenAI embedder (one embed call per memory, per fresh
        process — bounded by the network's memory count, typically <100).
        """
        data = {
            "memories": [
                {"id": m.id, "content": getattr(m, "content", str(m))}
                for m in net["all_memories"]
            ],
            "ingested_sessions": sorted(net["ingested_sessions"]),
        }
        path = self._persist_path(network_id)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        tmp.replace(path)

    def _get_network(self, network_id: str) -> Dict:
        if network_id not in self._networks:
            store = self._InMemoryStore(
                index={
                    "dims": 1536,
                    "embed": f"openai:{self._embed_model}",
                }
            )
            manager = self._create_memory_manager(f"openai:{self._model}")
            all_memories: List = []
            ingested_sessions: set = set()
            namespace = ("memories", network_id)

            path = self._persist_path(network_id)
            if path.exists():
                try:
                    with open(path) as f:
                        data = json.load(f)
                    for m in data.get("memories", []):
                        mi = _MemoryItem(id=m["id"], content=m["content"])
                        all_memories.append(mi)
                        # Repopulate vector index. store.put with an index-configured
                        # store triggers a synchronous embed call per item.
                        store.put(namespace, mi.id, {"content": mi.content})
                    for s in data.get("ingested_sessions", []):
                        ingested_sessions.add(s)
                    self.console.print(
                        f"   LangMem: loaded {len(all_memories)} memories "
                        f"from {path.name} ({len(ingested_sessions)} sessions)"
                    )
                except Exception as e:
                    self.console.print(
                        f"   ⚠️  Failed to load langmem persistence {path}: {e}. "
                        f"Starting empty.",
                        style="yellow",
                    )

            self._networks[network_id] = {
                "store": store,
                "manager": manager,
                "all_memories": all_memories,
                "ingested_sessions": ingested_sessions,
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
        if n_memories == 0:
            self.console.print(
                "   ⚠️  WARNING: 0 consolidated memories after ingestion — "
                "check langmem manager extraction and API key",
                style="yellow",
            )
        else:
            self.console.print(f"   LangMem store: {n_memories} consolidated memories")
            for m in all_memories[:3]:
                text = getattr(m, "content", str(m))
                self.console.print(f"     • {str(text)[:100]}")
        print_success(f"LangMem add: {total_sent} turns → {n_memories} consolidated memories, {len(errors)} errors")
        try:
            self._save_network(user_id, net)
            self.console.print(
                f"   LangMem: persisted {n_memories} memories to "
                f"{self._persist_path(user_id).name}"
            )
        except Exception as e:
            errors.append(f"persist error: {e}")
            self.console.print(f"   ⚠️  LangMem persist failed: {e}", style="yellow")
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
            all_memories = net["all_memories"]
            namespace = ("memories", user_id)

            results = store.search(namespace, query=query, limit=effective_k)
            duration_ms = (time.time() - start) * 1000

            retrieved = []
            for item in results:
                content = item.value.get("content", str(item.value))
                retrieved.append(content)

            if retrieved:
                context = "\n".join(f"- {m}" for m in retrieved)
            elif all_memories:
                # Fallback: store.search failed or returned nothing, but we have
                # consolidated memories in memory — return them all unordered.
                # This is better than returning empty context.
                self.console.print(
                    f"   ⚠️  store.search returned 0 results; falling back to "
                    f"all {len(all_memories)} consolidated memories",
                    style="yellow",
                )
                retrieved = [
                    getattr(m, "content", str(m)) for m in all_memories
                ]
                context = "\n".join(f"- {m}" for m in retrieved)
            else:
                context = "[No memories retrieved]"

        except Exception as e:
            self.console.print(
                f"   ⚠️  LangMem search error ({type(e).__name__}): {e}",
                style="yellow",
            )
            duration_ms = (time.time() - start) * 1000
            # Fallback to all_memories if available
            try:
                net = self._get_network(user_id)
                all_memories = net["all_memories"]
                if all_memories:
                    retrieved = [getattr(m, "content", str(m)) for m in all_memories]
                    context = "\n".join(f"- {m}" for m in retrieved)
                else:
                    retrieved = []
                    context = f"[Search failed: {type(e).__name__}]"
            except Exception:
                retrieved = []
                context = f"[Search failed: {type(e).__name__}]"

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
