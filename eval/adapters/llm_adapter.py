"""
LLM Adapter for SocialMemBench evaluation.

Uses the FULL DIALOGUE as context instead of a memory system.
This is the mini-oracle baseline: GPT-4o-mini or Gemini Flash with full context.

Key behavior:
- add(): stores the dataset; no-op (no memory system)
- search(): returns the full formatted corpus as context for every question
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from eval.adapters.base import BaseAdapter
from eval.core.data_models import Dataset, AddResult, SearchResult
from eval.utils.logger import get_console, print_success


class LLMAdapter(BaseAdapter):
    """
    LLM adapter for direct dialogue-based evaluation (mini-oracle).

    add() is a no-op that stores the corpus.
    search() returns the full conversation as context — no retrieval.
    """

    def __init__(self, config: Dict[str, Any], output_dir: Optional[Path] = None):
        super().__init__(config, output_dir)
        self.console = get_console()
        self._dialogue_data: Optional[Dataset] = None
        self._dialogue_context: Optional[str] = None
        self.console.print("✅ LLMAdapter initialized", style="bold green")
        self.console.print("   Mode: Full dialogue as context (no memory system)")

    async def add(
        self,
        dataset: Dataset,
        user_id: str,
        days_to_process: Optional[List[str]] = None,
        **kwargs,
    ) -> AddResult:
        """Store dataset for later use (no actual add operation)."""
        self.console.print(f"\n{'='*60}", style="bold cyan")
        self.console.print("Stage: Add (LLM - No-op)", style="bold cyan")
        self.console.print(f"{'='*60}", style="bold cyan")

        self._dialogue_data = dataset
        self._dialogue_context = self._format_dialogue_as_context(dataset, days_to_process)

        if days_to_process:
            days = [d for d in dataset.days if d.date in days_to_process]
        else:
            days = dataset.days

        total_messages = sum(day.total_messages for day in days)

        self.console.print(f"   Dataset: {dataset.name}")
        self.console.print(f"   Sessions: {len(days)}")
        self.console.print(f"   Total messages: {total_messages}")
        self.console.print(f"   Context length: {len(self._dialogue_context):,} characters")

        print_success("LLM adapter: dialogue stored for context (no memory system)")

        return AddResult(
            success=True,
            days_processed=len(days),
            messages_sent=0,
            metadata={
                "mode": "llm_full_dialogue",
                "context_length": len(self._dialogue_context),
                "total_messages": total_messages,
            },
        )

    async def search(
        self,
        query: str,
        user_id: str,
        top_k: int = 10,
        **kwargs,
    ) -> SearchResult:
        """Return full dialogue as context (no actual search)."""
        question_id = kwargs.get("question_id", "unknown")

        if self._dialogue_context is None:
            raise ValueError("Dialogue context not initialized. Call add() first.")

        return SearchResult(
            question_id=question_id,
            query=query,
            retrieved_memories=[],
            context=self._dialogue_context,
            search_duration_ms=0.0,
            metadata={
                "mode": "llm_full_dialogue",
                "context_length": len(self._dialogue_context),
            },
        )

    def _format_dialogue_as_context(
        self,
        dataset: Dataset,
        days_to_process: Optional[List[str]] = None,
    ) -> str:
        """
        Format the corpus as a plain-text context string.

        Uses our session format (matching smb-evaluate-oracle):
            --- Session 1, {date} ---
            [Session 1, 2:47pm] Speaker: message
            ...
        """
        lines: List[str] = []

        if days_to_process:
            days = [d for d in dataset.days if d.date in days_to_process]
        else:
            days = dataset.days

        for session_idx, day in enumerate(days, start=1):
            # Session header
            lines.append(f"--- Session {session_idx}, {day.date} ---")
            lines.append("")

            # All groups (typically one group per session in SocialMemBench)
            for group_name in sorted(day.groups.keys()):
                messages = day.groups[group_name]
                for msg in messages:
                    # Format time as 12-hour clock
                    hour = msg.timestamp.hour
                    minute = msg.timestamp.minute
                    period = "am" if hour < 12 else "pm"
                    hour12 = hour % 12 or 12
                    time_str = f"{hour12}:{minute:02d}{period}"
                    lines.append(f"[Session {session_idx}, {time_str}] {msg.speaker}: {msg.content}")

            lines.append("")

        return "\n".join(lines)

    async def close(self):
        self._dialogue_data = None
        self._dialogue_context = None
