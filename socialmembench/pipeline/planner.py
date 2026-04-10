"""Scale planner — given a QA target, compute the network generation plan.

Usage:
    from socialmembench.pipeline.planner import plan_to_target, plan_milestone

    tasks = plan_to_target(target_qa=200, manifest=manifest)
    for task in tasks:
        print(task)  # {"tier": "medium", "group_type": "recreational", "group_size": 9}
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from socialmembench.config import (
    MILESTONES,
    TIER_CONFIG,
    TIER_GROUP_TYPES,
    tier_for_size,
)


@dataclass
class GenerationTask:
    tier: str
    group_type: str
    group_size: int
    sessions: int = field(init=False)
    departures: int = field(init=False)

    def __post_init__(self) -> None:
        cfg = TIER_CONFIG[self.tier]
        self.sessions = cfg["sessions"]
        self.departures = cfg["departures"]

    def skill_args(self) -> str:
        """Build the $ARGUMENTS string for smb-generate-network."""
        return (
            f"{self.group_type} {self.group_size} "
            f"--sessions {self.sessions} --departures {self.departures}"
        )

    def __repr__(self) -> str:
        return (
            f"GenerationTask(tier={self.tier}, group_type={self.group_type}, "
            f"group_size={self.group_size}, sessions={self.sessions}, "
            f"departures={self.departures})"
        )


def _pick_group_type(tier: str, existing_type_counts: dict[str, int]) -> str:
    """Pick the most underrepresented group type valid for this tier."""
    valid = TIER_GROUP_TYPES[tier]
    return min(valid, key=lambda t: existing_type_counts.get(t, 0))


def _pick_group_size(tier: str) -> int:
    """Pick a group size within the tier's range (default = config default)."""
    return TIER_CONFIG[tier]["group_size_default"]


def plan_to_target(
    target_qa: int,
    manifest,  # DatasetManifest — avoid circular import
    preferred_tiers: list[str] | None = None,
) -> list[GenerationTask]:
    """Compute what to generate to reach target_qa total QA pairs.

    Args:
        target_qa: desired total QA pairs after generation.
        manifest: current DatasetManifest (read before calling this).
        preferred_tiers: tiers to generate from (default: all). Use to
            restrict to ["medium"] when doing tier-validation step.

    Returns:
        Ordered list of GenerationTask objects to run sequentially.
    """
    current_qa = manifest.qa_pairs_total
    remaining = max(0, target_qa - current_qa)
    if remaining == 0:
        return []

    tiers = preferred_tiers or ["small", "medium", "large"]
    # Build current type counts across existing networks
    type_counts: dict[str, int] = dict(manifest.group_type_counts)

    tasks: list[GenerationTask] = []
    accumulated = 0

    while accumulated < remaining:
        # Pick the most underrepresented valid tier
        tier = min(tiers, key=lambda t: manifest.size_tier_counts.get(t, 0))
        group_type = _pick_group_type(tier, type_counts)
        group_size = _pick_group_size(tier)

        task = GenerationTask(tier=tier, group_type=group_type, group_size=group_size)
        tasks.append(task)

        accumulated += TIER_CONFIG[tier]["qa_yield_estimate"]
        # Update local counts so next iteration balances
        manifest.size_tier_counts[tier] = manifest.size_tier_counts.get(tier, 0) + 1
        type_counts[group_type] = type_counts.get(group_type, 0) + 1

    return tasks


def plan_milestone(
    milestone_name: str,
    manifest,
) -> list[GenerationTask]:
    """Compute generation plan for a named milestone.

    Respects the per-tier targets defined in MILESTONES.
    Only generates what's still missing (already-done networks count).
    """
    if milestone_name not in MILESTONES:
        raise ValueError(
            f"Unknown milestone: {milestone_name!r}. "
            f"Choose from: {list(MILESTONES.keys())}"
        )

    ms = MILESTONES[milestone_name]
    type_counts: dict[str, int] = dict(manifest.group_type_counts)
    tasks: list[GenerationTask] = []

    for tier in ["small", "medium", "large"]:
        target_key = f"target_{tier}"
        if target_key not in ms:
            continue
        target_count = ms[target_key]
        current_count = manifest.size_tier_counts.get(tier, 0)
        needed = max(0, target_count - current_count)

        for _ in range(needed):
            group_type = _pick_group_type(tier, type_counts)
            group_size = _pick_group_size(tier)
            task = GenerationTask(tier=tier, group_type=group_type, group_size=group_size)
            tasks.append(task)
            type_counts[group_type] = type_counts.get(group_type, 0) + 1
            manifest.size_tier_counts[tier] = manifest.size_tier_counts.get(tier, 0) + 1

    return tasks


def summarize_plan(tasks: list[GenerationTask], current_qa: int) -> str:
    """Human-readable summary of a generation plan."""
    if not tasks:
        return "Nothing to generate — already at target."

    by_tier: dict[str, int] = {}
    for t in tasks:
        by_tier[t.tier] = by_tier.get(t.tier, 0) + 1

    estimated_qa = sum(TIER_CONFIG[t.tier]["qa_yield_estimate"] for t in tasks)
    lines = [
        f"Plan: {len(tasks)} network(s) → ~{estimated_qa} new QA pairs "
        f"(total ~{current_qa + estimated_qa})",
        "",
        "Breakdown:",
    ]
    for tier, count in sorted(by_tier.items()):
        cfg = TIER_CONFIG[tier]
        lines.append(
            f"  {tier:<10} {count} network(s) × "
            f"(size={cfg['group_size_default']}, "
            f"sessions={cfg['sessions']}, "
            f"departures={cfg['departures']}) "
            f"≈ {count * cfg['qa_yield_estimate']} QA"
        )
    lines.append("")
    lines.append("Tasks (in order):")
    for i, t in enumerate(tasks, 1):
        lines.append(
            f"  {i:2}. {t.tier:<10} {t.group_type:<25} "
            f"size={t.group_size}  sessions={t.sessions}  departures={t.departures}"
        )
    return "\n".join(lines)
