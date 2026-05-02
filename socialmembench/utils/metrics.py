"""Dataset quality metrics for SocialMemBench.

Usage:
    python -m socialmembench.utils.metrics --data_dir data/
"""

from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict


def compute_metrics(data_dir: str = "data") -> dict:
    root = Path(data_dir)

    # ---- QA pairs ----
    qa_dir = root / "qa"
    qa_pairs = []
    if qa_dir.exists():
        for f in qa_dir.glob("*.jsonl"):
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        qa_pairs.append(json.loads(line))

    query_type_counts: dict[str, int] = defaultdict(int)
    difficulty_counts: dict[str, int] = defaultdict(int)
    qc1_scores: list[float] = []
    qc2_grounded: list[bool] = []
    qc3_flagged: list[bool] = []
    skill_versions: dict[str, set] = defaultdict(set)

    for qa in qa_pairs:
        qt = qa.get("query_type", "unknown")
        query_type_counts[qt] += 1
        difficulty_counts[qa.get("difficulty", "unknown")] += 1
        if qa.get("qc_phase1_score") is not None:
            qc1_scores.append(qa["qc_phase1_score"])
        if qa.get("qc_phase2_grounded") is not None:
            qc2_grounded.append(qa["qc_phase2_grounded"])
        if qa.get("qc_phase3_flagged") is not None:
            qc3_flagged.append(qa["qc_phase3_flagged"])
        skill_versions[qt].add(qa.get("skill_version", "v1.0"))

    # ---- Networks ----
    raw_dir = root / "raw"
    networks = []
    if raw_dir.exists():
        for f in raw_dir.glob("*.json"):
            with open(f) as fh:
                networks.append(json.load(fh))

    group_type_counts: dict[str, int] = defaultdict(int)
    group_size_counts: dict[int, int] = defaultdict(int)
    for net in networks:
        group_type_counts[net.get("group_type", "unknown")] += 1
        group_size_counts[net.get("group_size", 0)] += 1

    # ---- Conversations ----
    conv_dir = root / "conversations"
    session_counts: list[int] = []
    turn_counts: list[int] = []
    critic_scores: list[float] = []
    if conv_dir.exists():
        for f in conv_dir.glob("*.json"):
            with open(f) as fh:
                corpus = json.load(fh)
            sessions = corpus.get("sessions", [])
            session_counts.append(len(sessions))
            turn_counts.append(sum(len(s.get("turns", [])) for s in sessions))
            for s in sessions:
                cs = s.get("critic_scores") or {}
                if cs.get("overall"):
                    critic_scores.append(cs["overall"])

    def safe_mean(lst: list) -> float | None:
        return round(sum(lst) / len(lst), 3) if lst else None

    return {
        "dataset_summary": {
            "total_qa_pairs": len(qa_pairs),
            "total_networks": len(networks),
            "total_conversations": len(session_counts),
        },
        "qa_quality": {
            "query_type_distribution": dict(query_type_counts),
            "difficulty_distribution": dict(difficulty_counts),
            "qc_phase1_mean_score": safe_mean(qc1_scores),
            "qc_phase1_pass_rate": (
                round(sum(s >= 0.70 for s in qc1_scores) / len(qc1_scores), 3) if qc1_scores else None
            ),
            "qc_phase2_grounded_rate": (
                round(sum(qc2_grounded) / len(qc2_grounded), 3) if qc2_grounded else None
            ),
            "qc_phase3_flag_rate": (
                round(sum(qc3_flagged) / len(qc3_flagged), 3) if qc3_flagged else None
            ),
            "skill_versions": {k: sorted(v) for k, v in skill_versions.items()},
        },
        "network_coverage": {
            "group_type_distribution": dict(group_type_counts),
            "group_size_distribution": dict(group_size_counts),
        },
        "conversation_quality": {
            "mean_sessions_per_network": safe_mean(session_counts),
            "mean_turns_per_network": safe_mean(turn_counts),
            "mean_critic_score": safe_mean(critic_scores),
        },
    }


def print_metrics(data_dir: str = "data") -> None:
    metrics = compute_metrics(data_dir)

    print("\n=== SocialMemBench Dataset Metrics ===\n")
    ds = metrics["dataset_summary"]
    print(f"Total QA pairs:      {ds['total_qa_pairs']}")
    print(f"Total networks:      {ds['total_networks']}")
    print(f"Total conversations: {ds['total_conversations']}")

    print("\n--- QA Quality ---")
    qa = metrics["qa_quality"]
    print(f"Query type distribution: {qa['query_type_distribution']}")
    print(f"Difficulty distribution: {qa['difficulty_distribution']}")
    print(f"QC Phase 1 mean score:   {qa['qc_phase1_mean_score']}")
    print(f"QC Phase 1 pass rate:    {qa['qc_phase1_pass_rate']}")
    print(f"QC Phase 2 grounded:     {qa['qc_phase2_grounded_rate']}")
    print(f"QC Phase 3 flag rate:    {qa['qc_phase3_flag_rate']}")

    print("\n--- Network Coverage ---")
    nc = metrics["network_coverage"]
    print(f"Group types: {nc['group_type_distribution']}")
    print(f"Group sizes: {nc['group_size_distribution']}")

    print("\n--- Conversation Quality ---")
    cq = metrics["conversation_quality"]
    print(f"Mean sessions/network: {cq['mean_sessions_per_network']}")
    print(f"Mean turns/network:    {cq['mean_turns_per_network']}")
    print(f"Mean critic score:     {cq['mean_critic_score']}")
    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Print SocialMemBench dataset metrics")
    parser.add_argument("--data_dir", default="data", help="Path to data directory")
    args = parser.parse_args()
    print_metrics(args.data_dir)
