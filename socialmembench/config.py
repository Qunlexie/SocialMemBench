"""Tier configuration and dataset targets for SocialMemBench.

This is the single source of truth for what each tier means.
CLI commands and the scale planner derive all parameters from here.
"""

from __future__ import annotations

from typing import TypedDict


class TierConfig(TypedDict):
    group_size_default: int          # picked when user doesn't specify size
    group_size_range: tuple[int, int]
    sessions: int                    # number of sessions to generate
    turns_per_session: int           # target turns per session (passed to skill as guidance)
    departures: int                  # number of personas that depart (internal default)
    qa_yield_estimate: int           # expected QA pairs per network (used by planner)
    participation_rate_default: float  # for small, 1.0; medium/large: floor of range


TIER_CONFIG: dict[str, TierConfig] = {
    "small": {
        "group_size_default": 5,
        "group_size_range": (3, 6),
        "sessions": 5,
        "turns_per_session": 15,     # 10-25 range, target the middle
        "departures": 0,
        "qa_yield_estimate": 10,     # ~2.0 QA/session (5 sessions); nudged up from 8
        "participation_rate_default": 1.0,
    },
    "medium": {
        "group_size_default": 9,
        "group_size_range": (7, 14),
        "sessions": 8,
        "turns_per_session": 20,     # more members → more natural back-and-forth
        "departures": 1,
        "qa_yield_estimate": 20,     # ~2.5 QA/session (8 sessions); nudged up from 18
        "participation_rate_default": 0.7,
    },
    "large": {
        "group_size_default": 20,
        "group_size_range": (15, 30),
        "sessions": 12,
        "turns_per_session": 25,     # large groups generate more volume
        "departures": 3,
        "qa_yield_estimate": 35,     # ~2.9 QA/session (12 sessions); nudged up from 30
        "participation_rate_default": 0.5,
    },
}

# Which group types are valid per tier (from data-gen.md)
TIER_GROUP_TYPES: dict[str, list[str]] = {
    "small": [
        "close_friends",
        "family",
        "recreational",
        "interest_community",
        "acquaintance_network",
    ],
    "medium": [
        "close_friends",
        "family",
        "recreational",
        "interest_community",
        "acquaintance_network",
    ],
    # close_friends not realistic at large scale
    "large": [
        "family",
        "recreational",
        "interest_community",
        "acquaintance_network",
    ],
}

# All group types (for validation)
ALL_GROUP_TYPES = [
    "close_friends",
    "family",
    "recreational",
    "interest_community",
    "acquaintance_network",
]

# Named milestones from data-gen.md — the targets we're building toward
MILESTONES: dict[str, dict[str, int]] = {
    "tier-validation": {
        "total_networks": 15,
        "total_qa": 220,             # was 200; revised with qa_yield_estimate updates
        "target_small": 10,
        "target_medium": 5,
        "target_large": 5,
    },
    "first-scale": {
        "total_networks": 25,
        "total_qa": 850,             # was 800; revised
        "target_small": 10,
        "target_medium": 15,
        "target_large": 0,
    },
    "full-dataset": {
        "total_networks": 40,
        "total_qa": 1500,            # was 1350; revised
        "target_small": 10,
        "target_medium": 20,
        "target_large": 10,
    },
    "longitudinal": {
        "total_networks": 46,
        "total_qa": 1800,            # was 1650; revised
        "target_small": 10,
        "target_medium": 20,
        "target_large": 10,
        "target_longitudinal": 6,
    },
}


def tier_for_size(group_size: int) -> str:
    """Infer tier from group size."""
    if group_size <= TIER_CONFIG["small"]["group_size_range"][1]:
        return "small"
    if group_size <= TIER_CONFIG["medium"]["group_size_range"][1]:
        return "medium"
    return "large"
