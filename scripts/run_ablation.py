"""
Ablation runner: sweep answerer and top-k without touching baseline results.

Usage:
    python scripts/run_ablation.py --network grp_9c0d1e2f --condition naive_rag \
        --answerer gpt-4o --top-k 20

    python scripts/run_ablation.py --network grp_9c0d1e2f --condition graphiti \
        --answerer gemini-2.5-flash --top-k 10

Design guarantees:
- Writes only under data/results/ablation/{cond}/ans={ans}__k={k}/{network_id}.jsonl
  (defensive assertion refuses any other path). One file per network per cell
  keeps the blast radius of any single file loss to one network's work.
- Refuses to run for a memory condition unless the ingestion sentinel exists
  at data/results/{cond}/{net}.ingested (never re-ingests during ablation).
- Reuses adapter/config plumbing from eval.cli via `_build_memory_adapter`.
- Skip-if-exists dedup: keyed by qa_id within this network's file. Re-runs
  that would only produce already-scored rows are a no-op.
- Query-type filter supported to allow cheap smoke on a subset.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
_env = ROOT / ".env"
if _env.exists():
    for line in open(_env):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(ROOT))

from eval.cli import _build_memory_adapter, MEMORY_CONDITIONS, CONDITION_MODELS
from eval.adapters.llm_adapter import LLMAdapter
from eval.core.answerer import Answerer
from eval.core.data_bridge import load_corpus_as_dataset, load_qa_pairs
from eval.core.evaluator import Evaluator

DATA_DIR = ROOT / "data"
RESULTS_DIR = DATA_DIR / "results"
ABLATION_ROOT = RESULTS_DIR / "ablation"

ALL_CONDITIONS = MEMORY_CONDITIONS | set(CONDITION_MODELS.keys())


def out_path(condition: str, answerer: str, top_k: int, network_id: str) -> Path:
    p = ABLATION_ROOT / condition / f"ans={answerer}__k={top_k}" / f"{network_id}.jsonl"
    assert "ablation" in p.parts, f"Refusing to touch outside ablation tree: {p}"
    return p


async def run_one(network_id: str, condition: str, answerer: str, top_k: int,
                  query_types: Optional[List[str]] = None, force: bool = False) -> dict:
    print(f"\n{'='*70}")
    print(f"Ablation: {condition} | net={network_id} | ans={answerer} | k={top_k}")
    print(f"{'='*70}")

    op = out_path(condition, answerer, top_k, network_id)
    op.parent.mkdir(parents=True, exist_ok=True)

    dataset = load_corpus_as_dataset(network_id, DATA_DIR)
    qa_items = load_qa_pairs(network_id, DATA_DIR, query_types=query_types)
    if not qa_items:
        print(f"  no QA pairs (query_types={query_types}); skipping")
        return {"skipped": True, "reason": "no-qa"}

    existing: dict = {}
    if op.exists():
        with open(op) as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    existing[d.get("qa_id")] = d
    remaining = [qa for qa in qa_items if qa.question_id not in existing]
    if not remaining and not force:
        print(f"  all {len(qa_items)} QA already scored at this cell; skipping")
        return {"skipped": True, "reason": "all-scored", "n_qa": len(qa_items)}
    if force:
        remaining = qa_items
        existing = {}
    print(f"  {len(qa_items)} QA total; {len(remaining)} new to score")

    if condition in MEMORY_CONDITIONS:
        sentinel = RESULTS_DIR / condition / f"{network_id}.ingested"
        assert sentinel.exists(), (
            f"Missing ingest sentinel; refuse to run without pre-ingested memory: {sentinel}. "
            f"Ablations must not trigger re-ingestion.")
        adapter = _build_memory_adapter(condition, top_k=top_k)
        system_name = "default"
    else:
        adapter = LLMAdapter(config={})
        await adapter.add(dataset, user_id=network_id)
        system_name = "llm"

    print(f"  searching (k={top_k}) ...")
    search_results = []
    for qa in remaining:
        sr = await adapter.search(
            query=qa.question, user_id=network_id, top_k=top_k,
            question_id=qa.question_id,
            query_type=getattr(qa, "query_type", None),
        )
        search_results.append(sr)

    print(f"  answering with {answerer} ...")
    answerer_obj = Answerer(config={"model": answerer}, system_name=system_name)
    answer_results = await answerer_obj.generate_answers_batch(remaining, search_results)

    print(f"  evaluating ...")
    evaluator = Evaluator(system_name="llm")
    eval_result = await evaluator.evaluate(answer_results)
    dr_by_id = {dr["question_id"]: dr for dr in eval_result.detailed_results}

    # Row schema (10 fields). `question` and `ground_truth` are intentionally
    # omitted; both are recoverable from data/qa/{network_id}.jsonl via qa_id
    # + eval.core.data_bridge.load_qa_pairs (which applies the MC-letter
    # transform correctly), so re-storing them here would just duplicate.
    new_rows = []
    for a, sr in zip(answer_results, search_results):
        d = dr_by_id.get(a.question_id, {"score": 0.0, "rationale": "not evaluated"})
        meta = a.metadata if hasattr(a, "metadata") and a.metadata else {}
        new_rows.append({
            "qa_id": a.question_id,
            "network_id": network_id,
            "condition": condition,
            "answerer": answerer,
            "top_k": top_k,
            "query_type": meta.get("query_type", ""),
            "generated_answer": a.generated_answer,
            "score": d["score"],
            "score_rationale": d.get("rationale", ""),
            "context_words": len(sr.context.split()) if sr and sr.context else 0,
        })

    all_rows = list(existing.values()) + new_rows
    tmp = op.with_suffix(".jsonl.tmp")
    with open(tmp, "w") as f:
        for row in all_rows:
            f.write(json.dumps(row) + "\n")
    tmp.rename(op)

    mean_new = sum(r["score"] for r in new_rows) / len(new_rows)
    mean_all = sum(r["score"] for r in all_rows) / len(all_rows)
    print(f"  wrote {op.relative_to(ROOT)}")
    print(f"  mean(new)={mean_new:.3f} | mean(all)={mean_all:.3f} | n={len(all_rows)}")
    return {"skipped": False, "n_new": len(new_rows), "n_total": len(all_rows),
            "mean": mean_all, "path": str(op.relative_to(ROOT))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", required=True)
    ap.add_argument("--condition", required=True, choices=sorted(ALL_CONDITIONS))
    ap.add_argument("--answerer", required=True,
                    help="Model name for read-time answering (e.g. gpt-4o-mini, "
                         "gpt-4o, gemini-2.5-flash).")
    ap.add_argument("--top-k", type=int, required=True)
    ap.add_argument("--query-types", nargs="*", default=None,
                    help="Optional filter, e.g. --query-types Q4 Q5")
    ap.add_argument("--force", action="store_true",
                    help="Re-score all QAs even if the output file already contains them")
    args = ap.parse_args()

    asyncio.run(run_one(
        network_id=args.network,
        condition=args.condition,
        answerer=args.answerer,
        top_k=args.top_k,
        query_types=args.query_types,
        force=args.force,
    ))


if __name__ == "__main__":
    main()
