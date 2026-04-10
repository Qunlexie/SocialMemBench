"""
Zep local adapter for SocialMemBench Condition B evaluation.

Connects to a self-hosted Zep open-source server running via Docker.
No cloud API key needed — just a running local Zep instance.

To start Zep locally:
    docker run -d -p 8000:8000 ghcr.io/getzep/zep:latest

Install client:
    pip install zep-python

Configuration (eval/config/adapters/zep_local.yaml):
    base_url: "http://localhost:8000"
    top_k: 10

How it works:
- add(): creates a Zep session per network, adds each turn as a message
  with role_type="user" and role=speaker_name
- search(): uses Zep memory search against the session for this network
"""
import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from eval.adapters.base import BaseAdapter
from eval.core.data_models import Dataset, AddResult, SearchResult
from eval.utils.logger import get_console, print_success


class ZepLocalAdapter(BaseAdapter):
    """
    Zep local adapter using self-hosted Zep server.

    Requires:
        Zep server running locally (Docker)
        pip install zep-python
    """

    def __init__(self, config: Dict[str, Any], output_dir: Optional[Path] = None):
        super().__init__(config, output_dir)
        self.console = get_console()

        self.base_url = config.get("base_url", "http://localhost:8000")
        self.top_k = config.get("top_k", 10)
        self._sessions: Dict[str, str] = {}  # network_id → session_id

        try:
            from zep_python import ZepClient
        except ImportError:
            raise ImportError(
                "zep-python is required.\n"
                "Install with: pip install 'zep-python<2.0'\n"
                "Start Zep server: docker run -d -p 8000:8000 ghcr.io/getzep/zep:latest"
            )

        # Test connectivity before proceeding
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.base_url}/healthz", timeout=3)
        except Exception as e:
            raise ConnectionError(
                f"Cannot connect to Zep server at {self.base_url}.\n"
                "Start it with: docker run -d -p 8000:8000 ghcr.io/getzep/zep:latest\n"
                f"(Original error: {e})"
            )

        self.client = ZepClient(base_url=self.base_url)
        self.console.print("✅ ZepLocalAdapter initialized", style="bold green")
        self.console.print(f"   Zep server: {self.base_url}")

    async def add(
        self,
        dataset: Dataset,
        user_id: str,
        days_to_process: Optional[List[str]] = None,
        **kwargs,
    ) -> AddResult:
        """
        Ingest conversation turns into Zep.

        Creates one Zep session per network (session_id = network_id).
        Each turn is added as a message with role=speaker_name so Zep
        can build per-speaker memory.
        """
        from zep_python.message import Message

        self.console.print(f"\n{'='*60}", style="bold cyan")
        self.console.print("Stage: Add (Zep local)", style="bold cyan")
        self.console.print(f"{'='*60}", style="bold cyan")

        session_id = user_id  # one session per network

        # Create session if it doesn't exist
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.client.memory.add_session(session_id=session_id)
            )
        except Exception:
            pass  # session may already exist

        self._sessions[user_id] = session_id

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
                zep_messages = []
                for msg in messages:
                    zep_messages.append(
                        Message(
                            role=msg.speaker,
                            role_type="user",
                            content=msg.content,
                        )
                    )

                try:
                    await loop.run_in_executor(
                        None,
                        lambda msgs=zep_messages: self.client.memory.add(
                            session_id=session_id,
                            messages=msgs,
                        ),
                    )
                    total_sent += len(zep_messages)
                except Exception as e:
                    errors.append(str(e))
                    self.console.print(f"   ⚠️  Error: {e}", style="yellow")

        print_success(f"Zep add: {total_sent} turns ingested, {len(errors)} errors")

        return AddResult(
            success=len(errors) == 0,
            days_processed=len(days),
            messages_sent=total_sent,
            errors=errors,
            metadata={"session_id": session_id, "total_sent": total_sent},
        )

    async def search(
        self,
        query: str,
        user_id: str,
        top_k: int = 10,
        **kwargs,
    ) -> SearchResult:
        """Retrieve relevant memories from Zep for the question."""
        import time

        question_id = kwargs.get("question_id", "unknown")
        session_id = self._sessions.get(user_id, user_id)
        effective_top_k = top_k or self.top_k
        start = time.time()

        loop = asyncio.get_event_loop()

        try:
            results = await loop.run_in_executor(
                None,
                lambda: self.client.memory.search(
                    session_id=session_id,
                    text=query,
                    limit=effective_top_k,
                ),
            )
            duration_ms = (time.time() - start) * 1000

            retrieved = []
            for r in (results or []):
                if hasattr(r, "message") and r.message:
                    text = f"[{r.message.role}] {r.message.content}"
                elif hasattr(r, "summary") and r.summary:
                    text = r.summary.content
                else:
                    text = str(r)
                retrieved.append(text)

            context = "\n".join(f"- {m}" for m in retrieved) if retrieved else "[No memories retrieved]"

        except Exception as e:
            self.console.print(f"   ⚠️  Zep search error: {e}", style="yellow")
            duration_ms = (time.time() - start) * 1000
            retrieved = []
            context = "[Search failed]"

        return SearchResult(
            question_id=question_id,
            query=query,
            retrieved_memories=retrieved,
            context=context,
            search_duration_ms=duration_ms,
            metadata={"session_id": session_id, "top_k": effective_top_k},
        )

    async def close(self):
        try:
            self.client.close()
        except Exception:
            pass
