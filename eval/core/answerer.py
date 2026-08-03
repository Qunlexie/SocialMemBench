"""
Answer generator for SocialMemBench QA evaluation.

Generates answers using LLM based on retrieved memories or full dialogue context.
Supports two question types:
- multiple_choice: Returns a single letter (A/B/C/D)
- open_ended: Returns free-text answer

Supports two model providers (selected by model name):
- OpenAI (OPENAI_API_KEY): gpt-4o-mini, gpt-4o, etc.
- Google Gemini (GOOGLE_API_KEY): gemini-2.0-flash, gemini-1.5-pro, etc.
"""
import asyncio
import os
import re
import time
import random
from typing import Dict, Any, List, Optional, Tuple

from openai import AsyncOpenAI
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

from eval.core.data_models import QAItem, SearchResult, AnswerResult
from eval.utils.config import load_yaml, get_config_path
from eval.utils.logger import get_console


class Answerer:
    """
    Answer generator using LLM.

    Loads prompts from eval/config/prompts.yaml and generates answers
    based on retrieved memories (memory systems) or full dialogue (llm adapter).
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        system_name: str = "default",
    ):
        """
        Initialize answerer.

        Args:
            config: Optional config dict overrides (merged over pipeline.yaml)
            system_name: "llm" uses llm_answer prompts; others use standard answer prompts
        """
        self.console = get_console()
        self.system_name = system_name

        # Load prompts config
        prompts_path = get_config_path("prompts.yaml")
        self.prompts_config = load_yaml(str(prompts_path))

        if system_name == "llm":
            self.mc_prompt = self.prompts_config.get("llm_answer", {}).get("multiple_choice", "")
            self.oe_prompt = self.prompts_config.get("llm_answer", {}).get("open_ended", "")
        else:
            self.mc_prompt = self.prompts_config.get("answer", {}).get("multiple_choice", "")
            self.oe_prompt = self.prompts_config.get("answer", {}).get("open_ended", "")

        # Load pipeline config
        try:
            pipeline_config_path = get_config_path("pipeline.yaml")
            pipeline_config = load_yaml(str(pipeline_config_path))
        except Exception:
            pipeline_config = {}

        answer_config = pipeline_config.get("answer", {})
        retry_config = pipeline_config.get("retry", {})

        if config:
            answer_config = {**answer_config, **config}

        # Model selection — determines which API to use
        self.model = answer_config.get("model", "gpt-4o-mini")
        api_timeout = answer_config.get("timeout", 300)

        if self.model.startswith("gemini"):
            api_key = answer_config.get("api_key") or os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("Gemini model requires GOOGLE_API_KEY env var.")
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                timeout=api_timeout,
            )
        else:
            api_key = answer_config.get("api_key") or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI model requires OPENAI_API_KEY env var.")
            self.client = AsyncOpenAI(api_key=api_key, timeout=api_timeout)

        self.temperature = answer_config.get("temperature", 0)
        self.max_tokens = answer_config.get("max_tokens", 1000)
        self.concurrency = answer_config.get("concurrency", 5)

        self.max_retries = retry_config.get("max_retries", 5)
        self.retry_delay = retry_config.get("retry_delay", 1.0)
        self.max_delay = retry_config.get("max_delay", 60.0)

        self.total_requests = 0

        self.console.print("✅ Answerer initialized", style="bold green")
        self.console.print(f"   Model: {self.model}")
        self.console.print(f"   System: {system_name}")
        self.console.print(f"   Concurrency: {self.concurrency}")

    async def generate_answer(
        self,
        qa_item: QAItem,
        search_result: SearchResult,
        **kwargs
    ) -> AnswerResult:
        """Generate answer for a single QA item."""
        start_time = time.time()

        if qa_item.question_type == "multiple_choice":
            answer = await self._answer_multiple_choice(qa_item, search_result)
        else:
            answer = await self._answer_open_ended(qa_item, search_result)

        duration_ms = (time.time() - start_time) * 1000

        return AnswerResult(
            question_id=qa_item.question_id,
            question=qa_item.question,
            question_type=qa_item.question_type,
            golden_answer=qa_item.answer,
            generated_answer=answer,
            search_result=search_result,
            answer_duration_ms=duration_ms,
            metadata=qa_item.metadata,
        )

    async def generate_answers_batch(
        self,
        qa_items: List[QAItem],
        search_results: List[SearchResult],
        concurrency: Optional[int] = None,
        **kwargs
    ) -> List[AnswerResult]:
        """Generate answers for multiple QA items concurrently."""
        if len(qa_items) != len(search_results):
            raise ValueError("qa_items and search_results must have same length")

        actual_concurrency = concurrency or self.concurrency
        semaphore = asyncio.Semaphore(actual_concurrency)
        completed = 0
        total = len(qa_items)
        results: List[Optional[AnswerResult]] = [None] * total

        async def generate_with_progress(idx: int, qa_item: QAItem, sr: SearchResult, progress, task_id) -> None:
            nonlocal completed
            async with semaphore:
                result = await self.generate_answer(qa_item, sr, **kwargs)
                results[idx] = result
                completed += 1
                progress.update(task_id, completed=completed)

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("[cyan]{task.completed}/{task.total}"),
            TimeRemainingColumn(),
            console=self.console,
        ) as progress:
            task_id = progress.add_task("Generating answers...", total=total)
            tasks = [
                generate_with_progress(idx, qa, sr, progress, task_id)
                for idx, (qa, sr) in enumerate(zip(qa_items, search_results))
            ]
            await asyncio.gather(*tasks)

        return results

    async def _answer_multiple_choice(self, qa_item: QAItem, search_result: SearchResult) -> str:
        options_text = "\n".join(qa_item.options) if qa_item.options else ""
        prompt = self.mc_prompt.format(
            context=search_result.context,
            question=qa_item.question,
            options=options_text
        )
        response, _ = await self._call_llm_with_retry(prompt)
        return self._parse_mc_answer(response)

    async def _answer_open_ended(self, qa_item: QAItem, search_result: SearchResult) -> str:
        prompt = self.oe_prompt.format(
            context=search_result.context,
            question=qa_item.question
        )
        response, _ = await self._call_llm_with_retry(prompt)
        if response.startswith("[LLM_CALL_FAILED]"):
            return "[FAILED]"
        return response.strip() if response else "[EMPTY]"

    async def _call_llm_with_retry(self, prompt: str) -> Tuple[str, bool]:
        """Call LLM with exponential backoff retry."""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                self.total_requests += 1
                return response.choices[0].message.content or "", False

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = min(self.retry_delay * (2 ** attempt) + random.uniform(0, 1), self.max_delay)
                    self.console.print(
                        f"   ⚠️  LLM call failed (attempt {attempt + 1}/{self.max_retries}), "
                        f"retrying in {delay:.1f}s: {str(e)[:60]}",
                        style="yellow"
                    )
                    await asyncio.sleep(delay)

        self.total_requests += 1
        self.console.print(f"   ❌ LLM call failed after {self.max_retries} attempts: {last_error}", style="red")
        return "[LLM_CALL_FAILED]", False

    def _parse_mc_answer(self, response: str) -> str:
        """Extract single letter (A/B/C/D) from LLM response."""
        if response.startswith("[LLM_CALL_FAILED]"):
            return "[FAILED]"

        response = response.strip().upper()
        if not response:
            return "[EMPTY]"

        if len(response) == 1 and response in "ABCD":
            return response

        # Explicit "answer/pick/choice is X" wins over incidental letters
        # earlier in the response (e.g., when the LLM restates options).
        match = re.search(r'(?:answer|choice|option|select|pick)(?:\s+is)?[:\s]+([ABCD])\b',
                          response, re.IGNORECASE)
        if match:
            return match.group(1).upper()

        match = re.search(r'\b([ABCD])[.):,\s]', response)
        if match:
            return match.group(1)

        if response[0] in "ABCD" and (len(response) == 1 or not response[1].isalpha()):
            return response[0]
        if response[-1] in "ABCD" and (len(response) == 1 or not response[-2].isalpha()):
            return response[-1]

        # Fallback: verbose responses (esp. gemini) often reason then conclude
        # with a bare letter. Take the last standalone A/B/C/D in the string.
        candidates = re.findall(r'\b([ABCD])\b', response)
        if candidates:
            return candidates[-1]

        return "[INVALID]"
