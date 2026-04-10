"""
Mem0 local adapter for SocialMemBench Condition B evaluation.

Uses the mem0ai Python library with a local Chroma vector store and
GPT-4o-mini as the LLM + embedding backend. No cloud API — fully local.

Install:
    pip install mem0ai chromadb openai

Configuration (eval/config/adapters/mem0_local.yaml):
    model: "gpt-4o-mini"
    chroma_path: "./data/.mem0_chroma"
    collection_name: "socialmembench"
    top_k: 10

How it works:
- add(): sends each turn as "[Speaker: Name] message" with user_id=network_id
- search(): retrieves top_k relevant memories for the question text
- Each network gets its own Chroma collection (collection_name + network_id)
  so networks don't bleed into each other across runs
"""
import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from eval.adapters.base import BaseAdapter
from eval.core.data_models import Dataset, AddResult, SearchResult
from eval.utils.logger import get_console, print_success


class Mem0LocalAdapter(BaseAdapter):
    """
    Local Mem0 adapter using mem0ai library + Chroma vector store.

    Requires:
        OPENAI_API_KEY (used by mem0ai for LLM and embeddings)
        pip install mem0ai chromadb
    """

    def __init__(self, config: Dict[str, Any], output_dir: Optional[Path] = None):
        super().__init__(config, output_dir)
        self.console = get_console()

        api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Mem0LocalAdapter requires OPENAI_API_KEY env var.")

        try:
            from mem0 import Memory
        except ImportError:
            raise ImportError(
                "mem0ai is required.\n"
                "Install with: pip install mem0ai chromadb"
            )

        chroma_path = str(Path(config.get("chroma_path", "./data/.mem0_chroma")).resolve())
        collection_name = config.get("collection_name", "socialmembench")
        model = config.get("model", "gpt-4o-mini")

        mem0_config = {
            "llm": {
                "provider": "openai",
                "config": {"model": model, "api_key": api_key},
            },
            "embedder": {
                "provider": "openai",
                "config": {"model": "text-embedding-3-small", "api_key": api_key},
            },
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": collection_name,
                    "path": chroma_path,
                },
            },
        }

        self._memory = Memory.from_config(mem0_config)
        self._network_id: Optional[str] = None
        self.top_k = config.get("top_k", 10)

        self.console.print("✅ Mem0LocalAdapter initialized", style="bold green")
        self.console.print(f"   LLM/Embedder: {model} (OpenAI)")
        self.console.print(f"   Vector store: local Chroma @ {chroma_path}")
        self.console.print(f"   Collection: {collection_name}")

    async def add(
        self,
        dataset: Dataset,
        user_id: str,
        days_to_process: Optional[List[str]] = None,
        **kwargs,
    ) -> AddResult:
        """
        Ingest conversation turns into local Mem0.

        Each turn is stored as "[Speaker: Name] message" with user_id=network_id.
        Speaker attribution is embedded in the text so the LLM backend can
        extract and store person-level facts.
        """
        self.console.print(f"\n{'='*60}", style="bold cyan")
        self.console.print("Stage: Add (Mem0 local)", style="bold cyan")
        self.console.print(f"{'='*60}", style="bold cyan")

        self._network_id = user_id

        if days_to_process:
            days = [d for d in dataset.days if d.date in days_to_process]
        else:
            days = dataset.days

        total_sent = 0
        errors = []
        loop = asyncio.get_event_loop()

        for day in days:
            session_idx = day.metadata.get("session_index", day.date)
            self.console.print(f"   Session {session_idx} ({day.date})...")

            for group_name, messages in day.groups.items():
                for msg in messages:
                    content = f"[Speaker: {msg.speaker}] {msg.content}"
                    try:
                        await loop.run_in_executor(
                            None,
                            lambda c=content: self._memory.add(
                                c,
                                user_id=user_id,
                                metadata={
                                    "speaker": msg.speaker,
                                    "session": str(session_idx),
                                    "date": day.date,
                                },
                            ),
                        )
                        total_sent += 1
                    except Exception as e:
                        errors.append(str(e))
                        self.console.print(f"   ⚠️  Error: {e}", style="yellow")

        print_success(f"Mem0 add: {total_sent} turns ingested, {len(errors)} errors")

        return AddResult(
            success=len(errors) == 0,
            days_processed=len(days),
            messages_sent=total_sent,
            errors=errors,
            metadata={"user_id": user_id, "total_sent": total_sent},
        )

    async def search(
        self,
        query: str,
        user_id: str,
        top_k: int = 10,
        **kwargs,
    ) -> SearchResult:
        """Retrieve relevant memories from local Mem0 for the question."""
        import time

        question_id = kwargs.get("question_id", "unknown")
        effective_top_k = top_k or self.top_k
        start = time.time()

        loop = asyncio.get_event_loop()

        try:
            results = await loop.run_in_executor(
                None,
                lambda: self._memory.search(query, user_id=user_id, limit=effective_top_k),
            )
            duration_ms = (time.time() - start) * 1000

            # mem0ai returns list of dicts or {"results": [...]}
            if isinstance(results, dict):
                memories_raw = results.get("results", results.get("memories", []))
            elif isinstance(results, list):
                memories_raw = results
            else:
                memories_raw = []

            retrieved = []
            for r in memories_raw:
                text = r.get("memory", r.get("text", str(r))) if isinstance(r, dict) else str(r)
                retrieved.append(text)

            context = "\n".join(f"- {m}" for m in retrieved) if retrieved else "[No memories retrieved]"

        except Exception as e:
            self.console.print(f"   ⚠️  Mem0 search error: {e}", style="yellow")
            duration_ms = (time.time() - start) * 1000
            retrieved = []
            context = "[Search failed]"

        return SearchResult(
            question_id=question_id,
            query=query,
            retrieved_memories=retrieved,
            context=context,
            search_duration_ms=duration_ms,
            metadata={"user_id": user_id, "top_k": effective_top_k},
        )

    async def close(self):
        self._memory = None
