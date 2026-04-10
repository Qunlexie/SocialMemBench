"""
Re-score existing JSONL results with correct evaluation alignment.

The original evaluator appended MC results first, then OE results, causing
positional misalignment when zipped with answer_results. This script
re-evaluates each pair's generated_answer independently by qa_id.

Usage:
    python -m eval.tools.rescore --condition llm_mini
    python -m eval.tools.rescore --condition naive_rag
    python -m eval.tools.rescore --condition all

For MC questions (Q2, Q4, Q6): binary 1.0/0.0 via letter comparison.
For OE questions (Q1, Q3, Q5, Q7, Q8): LLM judge.

Reads:   data/results/{condition}/{network_id}.jsonl
         data/qa/{network_id}.jsonl   (to get correct_option + answer_format)
Writes:  data/results/{condition}/{network_id}.jsonl  (updated in-place)
         data/results/{condition}/{network_id}_summary.json  (updated)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
from pathlib import Path
from typing import Dict

# Load .env
_project_root = Path(__file__).parent.parent.parent
_env_file = _project_root / ".env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

from eval.utils.logger import get_console

DATA_DIR = _project_root / "data"
RESULTS_DIR = DATA_DIR / "results"

ALL_CONDITIONS = [
    "llm_mini", "llm_gemini", "naive_rag", "graphiti",
    "langmem", "cognee", "mem0_local", "smg",
]

# MC query types — evaluated by letter comparison only
MC_TYPES = {"Q2", "Q4", "Q6"}


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
    if response and response[0] in "ABCD" and (len(response) == 1 or not response[1].isalpha()):
        return response[0]
    return response


def _score_mc(generated: str, correct_option: str) -> tuple:
    gen_letter = _parse_mc_answer(generated)
    gold_letter = correct_option.strip().upper()
    if len(gold_letter) > 1 and gold_letter[0] in "ABCD":
        gold_letter = gold_letter[0]
    match = gen_letter == gold_letter
    return (1.0, "exact letter match") if match else (0.0, "wrong letter")


async def _score_oe(client, model: str, question: str, golden: str, generated: str,
                    max_retries: int = 5) -> tuple:
    """LLM judge for open-ended questions."""
    judge_prompt = f"""You are evaluating a question-answering system on social group memory tasks.

Question: {question}

Golden answer: {golden}

Generated answer: {generated}

Score the generated answer from 0.0 to 1.0:
- 1.0: Correct — same meaning, correct attribution, all required parts present
- 0.7-0.9: Mostly correct — right answer but one part missing or slightly imprecise
- 0.4-0.6: Partial — right direction but wrong detail, missing key element, or ambiguous
- 0.0-0.3: Wrong — incorrect attribution, wrong answer, contradiction, or no answer

Return JSON: {{"score": <float 0.0-1.0>, "rationale": "<one sentence>"}}"""

    for attempt in range(max_retries):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a precise evaluator. Return only valid JSON."},
                    {"role": "user", "content": judge_prompt},
                ],
                temperature=0,
            )
            content = resp.choices[0].message.content or ""
            # Parse JSON
            if "{" in content and "}" in content:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                data = json.loads(content[json_start:json_end])
                score = max(0.0, min(1.0, float(data.get("score", 0.0))))
                rationale = str(data.get("rationale", ""))
                return score, rationale
        except Exception as e:
            if attempt < max_retries - 1:
                delay = min(1.5 * (2 ** attempt) + random.uniform(0, 1), 30.0)
                await asyncio.sleep(delay)
    return 0.0, "judge failed"


async def rescore_condition(condition: str, dry_run: bool = False):
    """Re-score all JSONL files for a condition."""
    from openai import AsyncOpenAI

    console = get_console()
    results_dir = RESULTS_DIR / condition
    if not results_dir.exists():
        console.print(f"No results for condition '{condition}' at {results_dir}", style="red")
        return

    # Use Gemini as judge (same as evaluator.py default)
    google_key = os.environ.get("GOOGLE_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if google_key:
        client = AsyncOpenAI(
            api_key=google_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        judge_model = "gemini-2.5-flash"
    else:
        client = AsyncOpenAI(api_key=openai_key)
        judge_model = "gpt-4o-mini"

    jsonl_files = list(results_dir.glob("*.jsonl"))
    console.print(f"\nRe-scoring condition: [bold]{condition}[/bold] ({len(jsonl_files)} networks)")
    console.print(f"Judge model: {judge_model}")

    for jsonl_path in sorted(jsonl_files):
        network_id = jsonl_path.stem
        console.print(f"\n  Network: [cyan]{network_id}[/cyan]")

        # Load existing pairs
        pairs = []
        with open(jsonl_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    pairs.append(json.loads(line))

        # Load QA pairs for correct_option lookup
        qa_path = DATA_DIR / "qa" / f"{network_id}.jsonl"
        qa_by_id: Dict[str, dict] = {}
        if qa_path.exists():
            with open(qa_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        qa = json.loads(line)
                        qa_by_id[qa["qa_id"]] = qa

        # Re-score each pair
        updated_pairs = []
        oe_tasks = []

        for p in pairs:
            qa_id = p["qa_id"]
            qa = qa_by_id.get(qa_id, {})
            query_type = p.get("query_type", "") or qa.get("query_type", "")
            answer_format = qa.get("answer_format", "long_form")
            correct_option = qa.get("correct_option")

            if answer_format == "multiple_choice" and correct_option:
                score, rationale = _score_mc(p["generated_answer"], correct_option)
                updated_pairs.append({**p, "score": score, "score_rationale": rationale})
            else:
                # OE — needs LLM judge
                oe_tasks.append((len(updated_pairs), p))
                updated_pairs.append(None)  # placeholder

        # Run OE evaluations concurrently (max 5 at a time)
        if oe_tasks:
            sem = asyncio.Semaphore(5)

            async def eval_one(idx, pair):
                async with sem:
                    score, rationale = await _score_oe(
                        client, judge_model,
                        pair["question"], pair["ground_truth"], pair["generated_answer"]
                    )
                    updated_pairs[idx] = {**pair, "score": score, "score_rationale": rationale}

            await asyncio.gather(*[eval_one(idx, pair) for idx, pair in oe_tasks])

        # Count correctly scored
        total = len(updated_pairs)
        mc_pairs = [p for p in updated_pairs if p is not None and p.get("score_rationale") in ("exact letter match", "wrong letter")]
        oe_pairs = [p for p in updated_pairs if p is not None and p not in mc_pairs]
        console.print(f"    MC: {len(mc_pairs)} pairs re-scored | OE: {len(oe_pairs)} pairs re-scored")

        if dry_run:
            for p in updated_pairs[:3]:
                if p:
                    console.print(f"      {p['qa_id']} {p['query_type']} → score={p['score']:.2f} ({p['score_rationale'][:50]})")
            continue

        # Write updated JSONL
        with open(jsonl_path, "w") as f:
            for p in updated_pairs:
                if p is not None:
                    f.write(json.dumps(p) + "\n")

        # Recompute and write summary
        valid_pairs = [p for p in updated_pairs if p is not None]
        by_qt: dict = {}
        for p in valid_pairs:
            qt = p.get("query_type", "")
            if qt not in by_qt:
                by_qt[qt] = {"count": 0, "total": 0.0}
            by_qt[qt]["count"] += 1
            by_qt[qt]["total"] += p["score"]

        total = len(valid_pairs)
        mean_score = sum(p["score"] for p in valid_pairs) / total if total else 0.0

        summary_path = results_dir / f"{network_id}_summary.json"
        summary = {}
        if summary_path.exists():
            with open(summary_path) as f:
                summary = json.load(f)

        summary["mean_score"] = round(mean_score, 3)
        summary["total_pairs"] = total
        summary["by_query_type"] = {
            qt: {"count": v["count"], "mean_score": round(v["total"] / v["count"], 3)}
            for qt, v in by_qt.items()
        }
        summary["low_scoring"] = [
            {"qa_id": p["qa_id"], "query_type": p.get("query_type", ""), "score": p["score"]}
            for p in valid_pairs if p["score"] < 0.5
        ]
        summary["rescored"] = True

        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        console.print(f"    Mean score: [bold green]{mean_score:.3f}[/bold green]")
        for qt in sorted(by_qt.keys()):
            v = by_qt[qt]
            ms = round(v["total"] / v["count"], 3)
            console.print(f"      {qt}: {ms:.3f} ({v['count']} pairs)")


def main():
    parser = argparse.ArgumentParser(description="Re-score existing evaluation results")
    parser.add_argument("--condition", required=True,
                        help="Condition name or 'all'")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing")
    args = parser.parse_args()

    conditions = ALL_CONDITIONS if args.condition == "all" else [args.condition]

    async def run_all():
        for cond in conditions:
            await rescore_condition(cond, dry_run=args.dry_run)

    asyncio.run(run_all())


if __name__ == "__main__":
    main()
