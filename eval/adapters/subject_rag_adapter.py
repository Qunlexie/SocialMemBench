"""
Subject RAG adapter — subject-indexed retrieval for social memory.

At ingestion: uses GPT-4o-mini to extract (subject, fact) pairs from each turn
and stores them as "[About: {subject}] {fact}" indexed by who the fact is ABOUT,
not who said it.

This directly addresses the speaker-subject conflation failure: when Nadia says
"Rafe hates steep trails", naive_rag indexes this under Nadia. Subject RAG
indexes it under Rafe.

Retrieval is unchanged cosine similarity — the improvement is entirely at the
indexing layer.

Config (eval/config/adapters/subject_rag.yaml):
    model: "gpt-4o-mini"
    embed_model: "text-embedding-3-small"
    chroma_path: "./data/.subject_rag_chroma"
    collection_name: "socialmembench_subject"
    top_k: 10
"""
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from eval.adapters.base import BaseAdapter
from eval.core.data_models import Dataset, AddResult, SearchResult
from eval.utils.logger import get_console, print_success

_EXTRACT_PROMPT = """\
You are reading a message from a group chat. Extract any facts about specific people mentioned.

Message: [{speaker}]: {message}

For each fact you find, output a JSON object with:
  "subject": the person the fact is about (could be the speaker or someone else mentioned)
  "fact": a concise statement of the fact (preference, behavior, opinion, relationship, history)

Return a JSON array. Return [] if no person-specific facts are present.
Only include facts clearly about a named person — not vague or group-level statements.

Examples:
  Input: [Nadia]: Rafe always goes straight to the pub after long runs, it's his thing
  Output: [{{"subject": "Rafe", "fact": "always goes to the pub after long runs"}}]

  Input: [Tom]: Great session today everyone
  Output: []

  Input: [Cass]: I didn't know I needed midweek runs in my life until now
  Output: [{{"subject": "Cass", "fact": "discovered she values midweek runs, hadn't done them before"}}]

Return only the JSON array, no other text."""


class SubjectRAGAdapter(BaseAdapter):
    """
    Subject RAG: index facts by who they are about, not who said them.
    Retrieval is standard cosine similarity — improvement is indexing-only.
    """

    def __init__(self, config: Dict[str, Any], output_dir: Optional[Path] = None):
        super().__init__(config, output_dir)
        self.console = get_console()

        api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("SubjectRAGAdapter requires OPENAI_API_KEY env var.")

        try:
            import chromadb
            from openai import OpenAI
        except ImportError:
            raise ImportError("Install with: pip install chromadb openai")

        self._model = config.get("model", "gpt-4o-mini")
        self._embed_model = config.get("embed_model", "text-embedding-3-small")
        self._top_k = config.get("top_k", 10)
        chroma_path = str(Path(config.get("chroma_path", "./data/.subject_rag_chroma")).resolve())
        collection_name = config.get("collection_name", "socialmembench_subject")

        self._oai = OpenAI(api_key=api_key, timeout=30.0)
        self._chroma = __import__("chromadb").PersistentClient(path=chroma_path)
        self._collection_name = collection_name
        self._collections: Dict[str, Any] = {}

        self.console.print("✅ SubjectRAGAdapter initialized", style="bold green")
        self.console.print(f"   Model: {self._model} | Embed: {self._embed_model}")

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

    def _extract_facts(self, speaker: str, message: str, session_idx: Any) -> List[str]:
        prompt = _EXTRACT_PROMPT.format(speaker=speaker, message=message)
        try:
            resp = self._oai.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=300,
            )
            raw = resp.choices[0].message.content.strip()
            facts = json.loads(raw)
            result = []
            for f in facts:
                subject = f.get("subject", "").strip()
                fact = f.get("fact", "").strip()
                if subject and fact:
                    result.append(f"[About: {subject}] {fact} (Session {session_idx})")
            # Always store raw turn as fallback context
            result.append(f"[{speaker}] {message} (Session {session_idx})")
            return result
        except Exception:
            return [f"[{speaker}] {message} (Session {session_idx})"]

    async def add(
        self,
        dataset: Dataset,
        user_id: str,
        days_to_process: Optional[List[str]] = None,
        **kwargs,
    ) -> AddResult:
        self.console.print(f"\n{'='*60}", style="bold cyan")
        self.console.print("Stage: Add (Subject RAG)", style="bold cyan")
        self.console.print(f"{'='*60}", style="bold cyan")

        collection = self._get_collection(user_id)
        days = [d for d in dataset.days if d.date in days_to_process] if days_to_process else dataset.days
        existing_ids = set(collection.get()["ids"]) if collection.count() > 0 else set()

        loop = asyncio.get_event_loop()
        total_sent = errors = 0
        BATCH = 50

        for day in days:
            session_idx = day.metadata.get("session_index", day.date)
            self.console.print(f"   Session {session_idx} ({day.date}) — extracting facts...")

            texts, ids, metas = [], [], []
            for group_name, messages in day.groups.items():
                for i, msg in enumerate(messages):
                    base_id = f"{user_id}_{day.date}_{group_name}_{i}"
                    if f"{base_id}_0" in existing_ids:
                        continue
                    extracted = await loop.run_in_executor(
                        None,
                        lambda s=msg.speaker, m=msg.content: self._extract_facts(s, m, session_idx),
                    )
                    for j, text in enumerate(extracted):
                        texts.append(text)
                        ids.append(f"{base_id}_{j}")
                        metas.append({
                            "speaker": msg.speaker,
                            "session": str(session_idx),
                            "date": day.date,
                        })

            for start in range(0, len(texts), BATCH):
                bt, bi, bm = texts[start:start+BATCH], ids[start:start+BATCH], metas[start:start+BATCH]
                try:
                    embeddings = await loop.run_in_executor(None, lambda t=bt: self._embed(t))
                    collection.upsert(embeddings=embeddings, documents=bt, ids=bi, metadatas=bm)
                    total_sent += len(bt)
                except Exception as e:
                    errors += 1
                    self.console.print(f"   ⚠️  Embed error: {e}", style="yellow")

        print_success(f"Subject RAG add: {total_sent} docs indexed, {errors} errors")
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

            context = "\n".join(f"- {m}" for m in retrieved) if retrieved else "[No facts retrieved]"

        except Exception as e:
            self.console.print(f"   ⚠️  Search error: {e}", style="yellow")
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
