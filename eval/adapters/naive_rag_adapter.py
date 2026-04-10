"""
Naive RAG adapter for SocialMemBench baseline evaluation.

No memory extraction — stores raw conversation turns directly in a Chroma
vector store using OpenAI embeddings, then retrieves top-k by semantic
similarity at query time. Represents the simplest possible retrieval baseline.

Useful as a floor comparison:
    naive_rag < mem0_local < (oracle)

Install:
    pip install chromadb openai  (both already installed via mem0ai)

Configuration (eval/config/adapters/naive_rag.yaml):
    model: "text-embedding-3-small"
    chroma_path: "./data/.naive_rag_chroma"
    collection_name: "socialmembench_rag"
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


class NaiveRAGAdapter(BaseAdapter):
    """
    Naive RAG: embed turns verbatim, retrieve by cosine similarity.
    No LLM extraction step — speaker + message stored as-is.
    """

    def __init__(self, config: Dict[str, Any], output_dir: Optional[Path] = None):
        super().__init__(config, output_dir)
        self.console = get_console()

        api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("NaiveRAGAdapter requires OPENAI_API_KEY env var.")

        try:
            import chromadb
            from openai import OpenAI
        except ImportError:
            raise ImportError("Install with: pip install chromadb openai")

        self._embed_model = config.get("model", "text-embedding-3-small")
        self._top_k = config.get("top_k", 10)
        chroma_path = str(Path(config.get("chroma_path", "./data/.naive_rag_chroma")).resolve())
        collection_name = config.get("collection_name", "socialmembench_rag")

        self._oai = OpenAI(api_key=api_key)
        self._chroma = chromadb.PersistentClient(path=chroma_path)
        self._collection_name = collection_name
        self._collections: Dict[str, Any] = {}  # network_id → chroma collection

        self.console.print("✅ NaiveRAGAdapter initialized", style="bold green")
        self.console.print(f"   Embedding model: {self._embed_model}")
        self.console.print(f"   Chroma: {chroma_path}")

    def _get_collection(self, network_id: str):
        if network_id not in self._collections:
            name = f"{self._collection_name}_{network_id}"
            self._collections[network_id] = self._chroma.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[network_id]

    def _embed(self, texts: List[str]) -> List[List[float]]:
        response = self._oai.embeddings.create(model=self._embed_model, input=texts)
        return [r.embedding for r in response.data]

    async def add(
        self,
        dataset: Dataset,
        user_id: str,
        days_to_process: Optional[List[str]] = None,
        **kwargs,
    ) -> AddResult:
        """Store each turn verbatim as '[Speaker] message' with its embedding."""
        self.console.print(f"\n{'='*60}", style="bold cyan")
        self.console.print("Stage: Add (Naive RAG)", style="bold cyan")
        self.console.print(f"{'='*60}", style="bold cyan")

        collection = self._get_collection(user_id)
        days = [d for d in dataset.days if d.date in days_to_process] if days_to_process else dataset.days

        # Check what's already indexed (incremental)
        existing_ids = set(collection.get()["ids"]) if collection.count() > 0 else set()

        total_sent = errors = 0
        loop = asyncio.get_event_loop()
        BATCH = 100  # embed in batches to stay under token limits

        for day in days:
            session_idx = day.metadata.get("session_index", day.date)
            self.console.print(f"   Session {session_idx} ({day.date})...")

            texts, ids, metas = [], [], []
            for group_name, messages in day.groups.items():
                for i, msg in enumerate(messages):
                    doc_id = f"{user_id}_{day.date}_{group_name}_{i}"
                    if doc_id in existing_ids:
                        continue
                    text = f"[{msg.speaker}] {msg.content}"
                    texts.append(text)
                    ids.append(doc_id)
                    metas.append({
                        "speaker": msg.speaker,
                        "session": str(session_idx),
                        "date": day.date,
                    })

            # Embed and upsert in batches
            for start in range(0, len(texts), BATCH):
                batch_t = texts[start:start + BATCH]
                batch_i = ids[start:start + BATCH]
                batch_m = metas[start:start + BATCH]
                try:
                    embeddings = await loop.run_in_executor(None, lambda t=batch_t: self._embed(t))
                    collection.upsert(embeddings=embeddings, documents=batch_t, ids=batch_i, metadatas=batch_m)
                    total_sent += len(batch_t)
                except Exception as e:
                    errors += 1
                    self.console.print(f"   ⚠️  Embed error: {e}", style="yellow")

        print_success(f"Naive RAG add: {total_sent} turns indexed, {errors} errors")
        return AddResult(
            success=errors == 0,
            days_processed=len(days),
            messages_sent=total_sent,
            errors=[],
            metadata={"user_id": user_id, "total_indexed": collection.count()},
        )

    async def search(
        self,
        query: str,
        user_id: str,
        top_k: int = 10,
        **kwargs,
    ) -> SearchResult:
        """Embed query and retrieve top-k most similar turns."""
        question_id = kwargs.get("question_id", "unknown")
        effective_k = top_k or self._top_k
        start = time.time()

        loop = asyncio.get_event_loop()
        try:
            collection = self._get_collection(user_id)
            query_embedding = await loop.run_in_executor(None, lambda: self._embed([query])[0])
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(effective_k, collection.count()),
                include=["documents", "metadatas", "distances"],
            )
            duration_ms = (time.time() - start) * 1000

            docs = results["documents"][0] if results["documents"] else []
            metas = results["metadatas"][0] if results["metadatas"] else []

            retrieved = []
            for doc, meta in zip(docs, metas):
                session = meta.get("session", "?")
                retrieved.append(f"[Session {session}] {doc}")

            context = "\n".join(f"- {m}" for m in retrieved) if retrieved else "[No turns retrieved]"

        except Exception as e:
            self.console.print(f"   ⚠️  RAG search error: {e}", style="yellow")
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
        pass
