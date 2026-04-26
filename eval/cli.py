"""
SocialMemBench evaluation CLI.

Usage:
    python -m eval.cli --network grp_1a2b3c4d --condition llm_mini
    python -m eval.cli --network grp_1a2b3c4d --condition llm_gemini
    python -m eval.cli --network grp_1a2b3c4d --condition mem0_local
    python -m eval.cli --network grp_1a2b3c4d --condition zep_local
    python -m eval.cli --network grp_1a2b3c4d --condition naive_rag
    python -m eval.cli --network grp_1a2b3c4d --condition graphiti
    python -m eval.cli --network grp_1a2b3c4d --condition langmem
    python -m eval.cli --network grp_1a2b3c4d --condition cognee
    python -m eval.cli --network grp_1a2b3c4d --condition llm_mini --query-types Q1 Q4 Q5
    python -m eval.cli --network grp_1a2b3c4d --condition llm_mini --sessions 3

Conditions:
    llm_mini      GPT-4o-mini, full context (mini-oracle baseline)
    llm_gemini    Gemini-2.5-Flash, full context (mini-oracle baseline)
    mem0_local    Mem0 + local Chroma + GPT-4o-mini
    zep_local     Zep self-hosted via Docker
    naive_rag     Raw turn storage + cosine retrieval (no LLM extraction)
    graphiti      Graphiti knowledge graph with embedded Kuzu DB (smb310 env)
    langmem       LangMem reflection + consolidation memory (smb310 env)
    cognee        Cognee batch doc-to-graph with hybrid retrieval (smb310 env)
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Load .env from project root
_project_root = Path(__file__).parent.parent
_env_file = _project_root / ".env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

from eval.adapters.llm_adapter import LLMAdapter
from eval.core.answerer import Answerer
from eval.core.data_bridge import load_corpus_as_dataset, load_qa_pairs
from eval.core.evaluator import Evaluator
from eval.utils.config import load_yaml
from eval.utils.logger import get_console

DATA_DIR = _project_root / "data"
RESULTS_DIR = DATA_DIR / "results"
ADAPTER_CONFIG_DIR = _project_root / "eval" / "config" / "adapters"

# LLM-based conditions: use full context, model name as answerer
CONDITION_MODELS = {
    "llm_mini": "gpt-4o-mini",
    "llm_gemini": "gemini-2.5-flash",
}

# Memory system conditions: ingest → retrieve → answer (no full context)
MEMORY_CONDITIONS = {"mem0_local", "zep_local", "naive_rag", "graphiti", "langmem", "cognee", "smg", "smg_gemini"}

ALL_CONDITIONS = set(CONDITION_MODELS.keys()) | MEMORY_CONDITIONS

# Answerer prompt section for memory conditions ("answer" = retrieved memories as context)
MEMORY_SYSTEM_NAME = "default"


def _build_memory_adapter(condition: str, top_k: Optional[int] = None):
    """Instantiate the correct local memory adapter."""
    if condition == "mem0_local":
        from eval.adapters.mem0_adapter import Mem0LocalAdapter
        config = load_yaml(str(ADAPTER_CONFIG_DIR / "mem0_local.yaml"))
        if top_k is not None:
            config["top_k"] = top_k
        return Mem0LocalAdapter(config)
    elif condition == "zep_local":
        from eval.adapters.zep_local_adapter import ZepLocalAdapter
        config = load_yaml(str(ADAPTER_CONFIG_DIR / "zep_local.yaml"))
        if top_k is not None:
            config["top_k"] = top_k
        return ZepLocalAdapter(config)
    elif condition == "naive_rag":
        from eval.adapters.naive_rag_adapter import NaiveRAGAdapter
        config = load_yaml(str(ADAPTER_CONFIG_DIR / "naive_rag.yaml"))
        if top_k is not None:
            config["top_k"] = top_k
        return NaiveRAGAdapter(config)
    elif condition == "graphiti":
        from eval.adapters.graphiti_adapter import GraphitiAdapter
        config = load_yaml(str(ADAPTER_CONFIG_DIR / "graphiti.yaml"))
        if top_k is not None:
            config["top_k"] = top_k
        return GraphitiAdapter(config)
    elif condition == "langmem":
        from eval.adapters.langmem_adapter import LangMemAdapter
        config = load_yaml(str(ADAPTER_CONFIG_DIR / "langmem.yaml"))
        if top_k is not None:
            config["top_k"] = top_k
        return LangMemAdapter(config)
    elif condition == "cognee":
        from eval.adapters.cognee_adapter import CogneeAdapter
        config = load_yaml(str(ADAPTER_CONFIG_DIR / "cognee.yaml"))
        if top_k is not None:
            config["top_k"] = top_k
        return CogneeAdapter(config)
    elif condition == "smg":
        from eval.adapters.smg_adapter import SMGAdapter
        config = load_yaml(str(ADAPTER_CONFIG_DIR / "smg.yaml"))
        if top_k is not None:
            config["top_k"] = top_k
        return SMGAdapter(config)
    elif condition == "smg_gemini":
        from eval.adapters.smg_adapter import SMGAdapter
        config = load_yaml(str(ADAPTER_CONFIG_DIR / "smg_gemini.yaml"))
        if top_k is not None:
            config["top_k"] = top_k
        return SMGAdapter(config)
    else:
        raise ValueError(f"Unknown memory condition: {condition}")


async def run_eval(
    network_id: str,
    condition: str,
    query_types: Optional[List[str]] = None,
    sessions: Optional[int] = None,
    top_k: Optional[int] = None,
) -> dict:
    """Run the full eval pipeline for one network."""
    console = get_console()
    is_memory = condition in MEMORY_CONDITIONS
    model = CONDITION_MODELS.get(condition, "gpt-4o-mini")  # memory conditions use gpt-4o-mini for answering
    label = condition if is_memory else f"{condition} ({model})"

    console.print(f"\n{'='*60}", style="bold blue")
    console.print(f"SocialMemBench Eval: {network_id}", style="bold blue")
    console.print(f"Condition: {label}", style="bold blue")
    console.print(f"{'='*60}", style="bold blue")

    # 1. Load data
    dataset = load_corpus_as_dataset(network_id, DATA_DIR)
    qa_items = load_qa_pairs(network_id, DATA_DIR, query_types=query_types)

    if not qa_items:
        console.print("❌ No QA pairs found (check network_id and query_types)", style="red")
        sys.exit(1)

    console.print(f"   Sessions: {dataset.total_days} | QA pairs: {len(qa_items)}")

    # Optionally truncate to first N sessions
    if sessions is not None and sessions < dataset.total_days:
        dataset = dataset.get_days_subset(sessions)
        console.print(f"   Truncated to {sessions} sessions")

    # 2. Load existing results — skip qa_ids already scored (incremental)
    out_dir = RESULTS_DIR / condition
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / f"{network_id}.jsonl"

    existing_results: dict = {}
    if jsonl_path.exists():
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    p = json.loads(line)
                    existing_results[p["qa_id"]] = p

    new_qa_items = [qa for qa in qa_items if qa.question_id not in existing_results]
    skipped = len(qa_items) - len(new_qa_items)
    if skipped:
        console.print(f"   Skipping {skipped} already-scored pairs, running {len(new_qa_items)} new")
    if not new_qa_items:
        console.print("   All pairs already scored — nothing to do.", style="green")
        await _print_summary_from_existing(existing_results, network_id, condition, model, dataset, jsonl_path, out_dir, console)
        return {}

    # 3. Build adapter and ingest corpus
    # Persistent memory adapters (mem0, naive_rag, graphiti, langmem, cognee, smg) write
    # data to disk (Chroma, Kuzu, etc). A sentinel file prevents re-ingestion on reruns,
    # which would duplicate vector store entries and waste API calls.
    ingested_flag = out_dir / f"{network_id}.ingested"

    if is_memory:
        adapter = _build_memory_adapter(condition, top_k=top_k)
        system_name = MEMORY_SYSTEM_NAME
        if ingested_flag.exists():
            console.print(f"   Skipping ingestion — already done (sentinel: {ingested_flag.name})", style="cyan")
        else:
            await adapter.add(dataset, user_id=network_id)
            ingested_flag.touch()
    else:
        adapter = LLMAdapter(config={})
        system_name = "llm"
        await adapter.add(dataset, user_id=network_id)

    # 4. Search — retrieve context for each new question
    search_results = []
    for qa in new_qa_items:
        sr = await adapter.search(
            query=qa.question,
            user_id=network_id,
            question_id=qa.question_id,
            query_type=getattr(qa, "query_type", None),
        )
        search_results.append(sr)

    # 5. Answer (memory conditions use "answer" prompts; LLM uses "llm_answer" prompts)
    answerer = Answerer(
        config={"model": model},
        system_name=system_name,
    )
    answer_results = await answerer.generate_answers_batch(new_qa_items, search_results)

    # 6. Evaluate
    evaluator = Evaluator(system_name="llm")
    eval_result = await evaluator.evaluate(answer_results)

    # 7. Build new pair results and append to existing
    # Index detailed_results by question_id — evaluator processes MC and OE
    # in separate batches so positional zip is incorrect.
    dr_by_id = {dr["question_id"]: dr for dr in eval_result.detailed_results}

    new_pairs = []
    for ar, sr in zip(answer_results, search_results):
        dr = dr_by_id.get(ar.question_id, {"score": 0.0, "rationale": "not evaluated"})
        meta = ar.metadata if hasattr(ar, "metadata") and ar.metadata else {}
        context_words = len(sr.context.split()) if sr and sr.context else 0
        new_pairs.append({
            "qa_id": ar.question_id,
            "network_id": network_id,
            "query_type": meta.get("query_type", ""),
            "difficulty": meta.get("difficulty", ""),
            "question": ar.question,
            "ground_truth": ar.golden_answer,
            "generated_answer": ar.generated_answer,
            "score": dr["score"],
            "score_rationale": dr.get("rationale", ""),
            "context_words": context_words,
        })

    # Append new results to the JSONL (don't overwrite existing)
    with open(jsonl_path, "a", encoding="utf-8") as f:
        for p in new_pairs:
            f.write(json.dumps(p) + "\n")

    # All results (old + new) for summary
    all_pairs = list(existing_results.values()) + new_pairs

    # Group by query type
    by_query_type: dict = {}
    for p in all_pairs:
        qt = p["query_type"]
        if qt not in by_query_type:
            by_query_type[qt] = {"count": 0, "total_score": 0.0}
        by_query_type[qt]["count"] += 1
        by_query_type[qt]["total_score"] += p["score"]
    by_query_type_summary = {
        qt: {
            "count": v["count"],
            "mean_score": round(v["total_score"] / v["count"], 3),
        }
        for qt, v in by_query_type.items()
    }

    total = len(all_pairs)
    mean_score = sum(p["score"] for p in all_pairs) / total if total else 0.0
    context_word_counts = [p.get("context_words", 0) for p in all_pairs]
    mean_context_words = sum(context_word_counts) / total if total else 0

    summary = {
        "network_id": network_id,
        "condition": condition,
        "model": model,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "sessions_used": dataset.total_days,
        "total_pairs": total,
        "new_pairs_this_run": len(new_pairs),
        "mean_score": round(mean_score, 3),
        "mean_context_words": round(mean_context_words, 1),
        "by_query_type": by_query_type_summary,
        "low_scoring": [
            {"qa_id": p["qa_id"], "query_type": p["query_type"], "score": p["score"], "rationale": p["score_rationale"]}
            for p in all_pairs if p["score"] < 0.5
        ],
    }
    per_pair = all_pairs

    summary_path = out_dir / f"{network_id}_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Update manifest
    manifest_path = DATA_DIR / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        if network_id in manifest.get("networks", {}):
            manifest["networks"][network_id][condition] = {
                "mean_score": summary["mean_score"],
                "total_pairs": summary["total_pairs"],
                "evaluated_at": summary["evaluated_at"],
            }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    # 8. Print summary
    console.print(f"\nEval: {network_id} ({condition})")
    console.print(f"Total pairs: {summary['total_pairs']} | Mean score: {summary['mean_score']:.3f}\n")
    console.print("By query type:")
    for qt in sorted(by_query_type_summary.keys()):
        v = by_query_type_summary[qt]
        console.print(f"  {qt:<4}  {v['mean_score']:.3f}  ({v['count']} pairs)")
    if summary["low_scoring"]:
        console.print("\nLow-scoring pairs (score < 0.50):")
        for p in summary["low_scoring"]:
            console.print(f"  {p['qa_id']}  {p['query_type']}  {p['score']:.2f}  — {p['rationale']}")
    console.print(f"\nResults: {summary_path}")

    await adapter.close()
    return summary


async def _print_summary_from_existing(existing, network_id, condition, model, dataset, jsonl_path, out_dir, console):
    """Recompute and rewrite summary from fully-cached results."""
    all_pairs = list(existing.values())
    by_query_type: dict = {}
    for p in all_pairs:
        qt = p["query_type"]
        if qt not in by_query_type:
            by_query_type[qt] = {"count": 0, "total_score": 0.0}
        by_query_type[qt]["count"] += 1
        by_query_type[qt]["total_score"] += p["score"]
    by_qt = {qt: {"count": v["count"], "mean_score": round(v["total_score"] / v["count"], 3)} for qt, v in by_query_type.items()}
    total = len(all_pairs)
    mean = round(sum(p["score"] for p in all_pairs) / total, 3) if total else 0.0
    console.print(f"\nEval: {network_id} ({condition}) — all {total} pairs already scored")
    console.print(f"Mean score: {mean:.3f}\n")
    console.print("By query type:")
    for qt in sorted(by_qt.keys()):
        v = by_qt[qt]
        console.print(f"  {qt:<4}  {v['mean_score']:.3f}  ({v['count']} pairs)")
    console.print(f"\nResults: {jsonl_path}")


def main():
    parser = argparse.ArgumentParser(description="SocialMemBench evaluation CLI")
    parser.add_argument("--network", required=True, help="Network ID (e.g. grp_1a2b3c4d)")
    parser.add_argument(
        "--condition",
        required=True,
        choices=sorted(ALL_CONDITIONS),
        help="Evaluation condition",
    )
    parser.add_argument(
        "--query-types",
        nargs="+",
        help="Filter to specific query types (e.g. Q1 Q4 Q5)",
    )
    parser.add_argument(
        "--sessions",
        type=int,
        default=None,
        help="Use only first N sessions (for degradation curves)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Override retrieval top-k for memory conditions (default: from adapter config yaml)",
    )
    args = parser.parse_args()

    asyncio.run(
        run_eval(
            network_id=args.network,
            condition=args.condition,
            query_types=args.query_types,
            sessions=args.sessions,
            top_k=args.top_k,
        )
    )


if __name__ == "__main__":
    main()
