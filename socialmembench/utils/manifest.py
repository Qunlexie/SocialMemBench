"""
Dataset manifest — tracks all generated items, seeds, and progress.

This is the heart of the incremental scale design:
- Every run reads the manifest before generating
- Seeds are assigned sequentially from next_seed (never reused)
- Planted challenges are tracked to prevent duplicate QA pairs
- Query type counts are tracked so new runs target underrepresented types
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


MANIFEST_PATH = Path("data/manifest.json")


class VerifySummary(BaseModel):
    overall_pass: bool
    stage1_pass: Optional[bool] = None
    stage2_pass: Optional[bool] = None
    stage3_pass: Optional[bool] = None
    failure_count: int = 0
    verified_at: Optional[str] = None


class OracleEvalSummary(BaseModel):
    mean_score: float
    total_pairs: int
    evaluated_at: str


class NetworkEntry(BaseModel):
    network_id: str
    group_type: str
    group_size: int
    tier: str = "small"             # small | medium | large | longitudinal
    seed: int
    status: str = "pending"         # pending | stage1_done | stage2_done | complete | verified
    n_sessions: int = 0
    n_qa: int = 0
    consumed_challenge_ids: list[str] = Field(default_factory=list)
    verify: Optional[VerifySummary] = None
    oracle_eval: Optional[OracleEvalSummary] = None


class DatasetManifest(BaseModel):
    version: str = "1.0"
    next_seed: int = 42
    networks: dict[str, NetworkEntry] = Field(default_factory=dict)
    qa_pairs_total: int = 0
    query_type_counts: dict[str, int] = Field(
        default_factory=lambda: {q: 0 for q in ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"]}
    )
    group_type_counts: dict[str, int] = Field(
        default_factory=lambda: {
            g: 0 for g in [
                "close_friends", "family", "recreational",
                "interest_community", "acquaintance_network"
            ]
        }
    )
    size_tier_counts: dict[str, int] = Field(
        default_factory=lambda: {"small": 0, "medium": 0, "large": 0, "longitudinal": 0}
    )

    # --- Persistence ---

    @classmethod
    def load(cls, path: str | Path = MANIFEST_PATH) -> "DatasetManifest":
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        manifest = cls.model_validate(data)
        manifest._backfill_tiers()
        return manifest

    def _backfill_tiers(self) -> None:
        """Infer tier from group_size for any network missing a tier field,
        and recompute size_tier_counts from scratch."""
        from socialmembench.config import tier_for_size

        # Recompute from the ground up to stay in sync with network entries
        tier_counts: dict[str, int] = {"small": 0, "medium": 0, "large": 0, "longitudinal": 0}
        for entry in self.networks.values():
            if entry.tier == "small" and entry.group_size > 6:
                # tier field is stale default — infer from size
                entry.tier = tier_for_size(entry.group_size)
            tier_counts[entry.tier] = tier_counts.get(entry.tier, 0) + 1
        self.size_tier_counts = tier_counts

    def save(self, path: str | Path = MANIFEST_PATH) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

    # --- Seed management ---

    def claim_seed(self) -> int:
        """Reserve and return the next available seed, then increment."""
        seed = self.next_seed
        self.next_seed += 1
        return seed

    # --- Network registration ---

    def register_network(
        self,
        network_id: str,
        group_type: str,
        group_size: int,
        seed: int,
        tier: str = "small",
    ) -> NetworkEntry:
        entry = NetworkEntry(
            network_id=network_id,
            group_type=group_type,
            group_size=group_size,
            tier=tier,
            seed=seed,
        )
        self.networks[network_id] = entry
        return entry

    def mark_stage1_done(self, network_id: str) -> None:
        self.networks[network_id].status = "stage1_done"

    def mark_stage2_done(self, network_id: str, n_sessions: int) -> None:
        self.networks[network_id].status = "stage2_done"
        self.networks[network_id].n_sessions = n_sessions

    def mark_complete(self, network_id: str, n_qa: int) -> None:
        entry = self.networks[network_id]
        entry.status = "complete"
        entry.n_qa = n_qa
        self.group_type_counts[entry.group_type] = (
            self.group_type_counts.get(entry.group_type, 0) + 1
        )
        self.size_tier_counts[entry.tier] = (
            self.size_tier_counts.get(entry.tier, 0) + 1
        )

    def most_needed_tier(self, candidate_tiers: list[str] | None = None) -> str:
        """Return the tier with fewest networks, restricted to candidate_tiers if given."""
        tiers = candidate_tiers or list(self.size_tier_counts.keys())
        return min(tiers, key=lambda t: self.size_tier_counts.get(t, 0))

    # --- QA tracking ---

    def record_qa_pair(self, network_id: str, query_type: str, challenge_id: str) -> None:
        self.qa_pairs_total += 1
        self.query_type_counts[query_type] = self.query_type_counts.get(query_type, 0) + 1
        self.networks[network_id].n_qa += 1
        if challenge_id and challenge_id not in self.networks[network_id].consumed_challenge_ids:
            self.networks[network_id].consumed_challenge_ids.append(challenge_id)

    def is_challenge_consumed(self, network_id: str, challenge_id: str) -> bool:
        entry = self.networks.get(network_id)
        if not entry:
            return False
        return challenge_id in entry.consumed_challenge_ids

    # --- Prioritization helpers ---

    def most_needed_group_type(self) -> str:
        """Return the group type with fewest networks (for balanced generation)."""
        return min(self.group_type_counts, key=lambda k: self.group_type_counts[k])

    def most_needed_query_types(self, top_n: int = 3) -> list[str]:
        """Return query types with fewest QA pairs (target underrepresented types)."""
        sorted_types = sorted(self.query_type_counts, key=lambda k: self.query_type_counts[k])
        return sorted_types[:top_n]

    # --- Status display ---

    def summary(self) -> str:
        lines = [
            f"SocialMemBench Dataset — v{self.version}",
            f"  Networks: {len(self.networks)} ({sum(1 for n in self.networks.values() if n.status == 'complete')} complete)",
            f"  QA pairs: {self.qa_pairs_total}",
            f"  Next seed: {self.next_seed}",
            "",
            "  Query type distribution:",
        ]
        for qtype, count in sorted(self.query_type_counts.items()):
            lines.append(f"    {qtype}: {count}")
        lines.append("\n  Group type distribution:")
        for gtype, count in sorted(self.group_type_counts.items()):
            lines.append(f"    {gtype}: {count}")
        return "\n".join(lines)
