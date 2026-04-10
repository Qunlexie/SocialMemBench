"""
Evaluator for SocialMemBench QA evaluation.

Evaluates generated answers against golden answers using 0.0–1.0 scores:
- Multiple choice: 1.0 if correct letter, 0.0 otherwise
- Open-ended: LLM judge returns 0.0–1.0 score + rationale

Supports OpenAI (OPENAI_API_KEY) and Gemini (GOOGLE_API_KEY) via model name.
"""
import asyncio
import json
import os
import random
import re
from typing import Dict, Any, List, Optional, Union

from openai import AsyncOpenAI
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

from eval.core.data_models import AnswerResult, LightAnswerResult, EvaluationResult
from eval.utils.config import load_yaml, get_config_path
from eval.utils.logger import get_console

AnswerResultType = Union[AnswerResult, LightAnswerResult]


class Evaluator:
    """
    Evaluator for QA results using 0.0–1.0 scoring.

    Multiple choice: binary 1.0/0.0 via direct letter comparison.
    Open-ended: LLM judge returns a float score + rationale.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, system_name: str = "default"):
        self.console = get_console()
        self.system_name = system_name

        # Load prompts config
        prompts_path = get_config_path("prompts.yaml")
        self.prompts_config = load_yaml(str(prompts_path))

        judge_config = self.prompts_config.get("llm_judge", {})
        self.judge_system_prompt = judge_config.get("system_prompt", "")
        self.judge_user_prompt = judge_config.get("user_prompt", "")

        # Load pipeline config
        try:
            pipeline_config_path = get_config_path("pipeline.yaml")
            pipeline_config = load_yaml(str(pipeline_config_path))
        except Exception:
            pipeline_config = {}

        evaluate_config = pipeline_config.get("evaluate", {})
        retry_config = pipeline_config.get("retry", {})

        if config:
            evaluate_config = {**evaluate_config, **config}

        # Model selection — determines which API to use
        self.model = evaluate_config.get("model", "gemini-2.5-flash")
        api_timeout = evaluate_config.get("timeout", 120)

        if self.model.startswith("gemini"):
            api_key = evaluate_config.get("api_key") or os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("Gemini model requires GOOGLE_API_KEY env var.")
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                timeout=api_timeout,
            )
        else:
            api_key = evaluate_config.get("api_key") or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI model requires OPENAI_API_KEY env var.")
            self.client = AsyncOpenAI(api_key=api_key, timeout=api_timeout)

        self.concurrency = evaluate_config.get("concurrency", 10)
        self.max_retries = retry_config.get("max_retries", 5)
        self.retry_delay = retry_config.get("retry_delay", 1.0)
        self.max_delay = retry_config.get("max_delay", 60.0)

        self.console.print("✅ Evaluator initialized", style="bold green")
        self.console.print(f"   Model: {self.model}")
        self.console.print(f"   Concurrency: {self.concurrency}")

    async def evaluate(
        self,
        answer_results: List[AnswerResultType],
        concurrency: Optional[int] = None,
        **kwargs
    ) -> EvaluationResult:
        """Evaluate all answer results, returning 0.0–1.0 scores."""
        self.console.print(f"\n{'='*60}", style="bold magenta")
        self.console.print("Stage: Evaluate", style="bold magenta")
        self.console.print(f"{'='*60}", style="bold magenta")
        self.console.print(f"Total questions: {len(answer_results)}")

        mc_results = [r for r in answer_results if r.question_type == "multiple_choice"]
        oe_results = [r for r in answer_results if r.question_type == "open_ended"]

        self.console.print(f"   Multiple choice: {len(mc_results)}")
        self.console.print(f"   Open-ended: {len(oe_results)}")

        detailed_results = []

        # Multiple choice — binary 1.0/0.0
        mc_scores = []
        for result in mc_results:
            score = 1.0 if self._evaluate_mc(result) else 0.0
            mc_scores.append(score)
            detailed_results.append({
                "question_id": result.question_id,
                "question": result.question,
                "question_type": result.question_type,
                "golden_answer": result.golden_answer,
                "generated_answer": result.generated_answer,
                "score": score,
                "rationale": "exact letter match" if score == 1.0 else "wrong letter",
            })

        # Open-ended — LLM judge (0.0–1.0)
        oe_scores = []
        if oe_results:
            self.console.print("\n   Evaluating open-ended questions with LLM judge...")
            actual_concurrency = concurrency or self.concurrency
            oe_judgments = await self._evaluate_oe_batch_with_progress(oe_results, actual_concurrency)
            for result, (score, rationale) in zip(oe_results, oe_judgments):
                oe_scores.append(score)
                detailed_results.append({
                    "question_id": result.question_id,
                    "question": result.question,
                    "question_type": result.question_type,
                    "golden_answer": result.golden_answer,
                    "generated_answer": result.generated_answer,
                    "score": score,
                    "rationale": rationale,
                })

        all_scores = mc_scores + oe_scores
        total = len(answer_results)
        mean_score = sum(all_scores) / total if total > 0 else 0.0
        # "correct" = number of answers scoring >= 0.7 (for compatibility with EvaluationResult)
        correct = sum(1 for s in all_scores if s >= 0.7)

        accuracy_by_type = {}
        if mc_results:
            accuracy_by_type["multiple_choice"] = {
                "total": len(mc_results),
                "mean_score": sum(mc_scores) / len(mc_scores),
                "correct": sum(1 for s in mc_scores if s >= 0.7),
            }
        if oe_results:
            accuracy_by_type["open_ended"] = {
                "total": len(oe_results),
                "mean_score": sum(oe_scores) / len(oe_scores),
                "correct": sum(1 for s in oe_scores if s >= 0.7),
            }

        self.console.print(f"\n{'='*60}", style="bold magenta")
        self.console.print(f"✅ Evaluation complete:", style="bold green")
        self.console.print(f"   Total: {total} | Mean score: {mean_score:.3f} | Correct (≥0.7): {correct}")

        return EvaluationResult(
            total_questions=total,
            correct=correct,
            accuracy=mean_score,  # repurposed as mean_score
            accuracy_by_type=accuracy_by_type,
            detailed_results=detailed_results,
            metadata={"model": self.model},
        )

    def _evaluate_mc(self, result: AnswerResultType) -> bool:
        """Return True if generated answer matches the correct option letter."""
        generated = result.generated_answer.strip()
        if generated.startswith("[") and generated.endswith("]"):
            return False

        golden = result.golden_answer.strip().upper()
        if len(golden) > 1 and golden[0] in "ABCD" and golden[1] in ".):":
            golden = golden[0]

        generated = self._parse_mc_answer(generated)
        return generated == golden

    @staticmethod
    def _parse_mc_answer(response: str) -> str:
        response = response.strip().upper()
        if not response:
            return ""
        if len(response) == 1 and response in "ABCD":
            return response
        match = re.search(r'\b([ABCD])[.):,\s]', response)
        if match:
            return match.group(1)
        match = re.search(r'(?:answer|choice|option|select)[:\s]+([ABCD])\b', response, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        if response[0] in "ABCD" and (len(response) == 1 or not response[1].isalpha()):
            return response[0]
        if response[-1] in "ABCD" and (len(response) == 1 or not response[-2].isalpha()):
            return response[-1]
        return response

    async def _evaluate_oe_batch_with_progress(
        self,
        results: List[AnswerResultType],
        concurrency: int = 10,
    ) -> List[tuple]:
        """Returns list of (score: float, rationale: str) tuples."""
        semaphore = asyncio.Semaphore(concurrency)
        total = len(results)
        completed = 0
        judgments: List[Optional[tuple]] = [None] * total

        async def evaluate_one(idx: int, result: AnswerResultType, progress, task_id) -> None:
            nonlocal completed
            async with semaphore:
                score, rationale = await self._evaluate_oe_single(result)
                judgments[idx] = (score, rationale)
                completed += 1
                progress.update(task_id, completed=completed)

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold magenta]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("[cyan]{task.completed}/{task.total}"),
            TimeRemainingColumn(),
            console=self.console,
        ) as progress:
            task_id = progress.add_task("LLM Judge evaluating...", total=total)
            tasks = [evaluate_one(idx, r, progress, task_id) for idx, r in enumerate(results)]
            await asyncio.gather(*tasks)

        return judgments

    async def _evaluate_oe_single(self, result: AnswerResultType) -> tuple:
        """Returns (score: float, rationale: str)."""
        return await self._call_llm_judge_with_retry(
            question=result.question,
            golden_answer=result.golden_answer,
            generated_answer=result.generated_answer,
        )

    async def _call_llm_judge_with_retry(
        self,
        question: str,
        golden_answer: str,
        generated_answer: str,
    ) -> tuple:
        """Call LLM judge with exponential backoff. Returns (score: float, rationale: str)."""
        user_prompt = self.judge_user_prompt.format(
            question=question,
            golden_answer=golden_answer,
            generated_answer=generated_answer,
        )
        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.judge_system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0,
                )
                content = response.choices[0].message.content or ""
                return self._parse_judge_response(content)

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = min(self.retry_delay * (2 ** attempt) + random.uniform(0, 1), self.max_delay)
                    self.console.print(
                        f"   ⚠️  LLM judge failed (attempt {attempt + 1}/{self.max_retries}), "
                        f"retrying in {delay:.1f}s: {str(e)[:60]}",
                        style="yellow",
                    )
                    await asyncio.sleep(delay)

        self.console.print(f"   ❌ LLM judge failed after {self.max_retries} attempts: {last_error}", style="red")
        return 0.0, "judge failed"

    def _parse_judge_response(self, content: str) -> tuple:
        """Parse JSON response from judge. Returns (score: float, rationale: str)."""
        try:
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                content_json = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                content_json = content[json_start:json_end].strip()
            elif "{" in content and "}" in content:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                content_json = content[json_start:json_end]
            else:
                content_json = content

            result = json.loads(content_json)
            score = float(result.get("score", 0.0))
            score = max(0.0, min(1.0, score))
            rationale = str(result.get("rationale", ""))
            return score, rationale

        except (json.JSONDecodeError, KeyError, ValueError):
            # Fallback: look for a float in the response
            match = re.search(r'\b(0\.\d+|1\.0|0|1)\b', content)
            if match:
                score = float(match.group(1))
                return max(0.0, min(1.0, score)), "parsed from text"
            return 0.0, "parse failed"
