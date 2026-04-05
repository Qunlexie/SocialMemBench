"""Persona and ego-network schemas for SocialMemBench Stage 1."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class GroupType(str, Enum):
    CLOSE_FRIENDS = "close_friends"
    FAMILY = "family"
    RECREATIONAL = "recreational"
    INTEREST_COMMUNITY = "interest_community"
    ACQUAINTANCE_NETWORK = "acquaintance_network"


class BigFiveProfile(BaseModel):
    openness: Literal["High", "Medium", "Low"]
    conscientiousness: Literal["High", "Medium", "Low"]
    extraversion: Literal["High", "Medium", "Low"]
    agreeableness: Literal["High", "Medium", "Low"]
    neuroticism: Literal["High", "Medium", "Low"]


class CommunicationProfile(BaseModel):
    formality: Literal["Casual", "Semi-formal", "Formal"]
    verbosity: Literal["Terse", "Concise", "Verbose"]
    emoji_use: Literal["Never", "Rare", "Moderate", "Frequent"]
    humor: Literal["Dry", "Minimal", "Playful", "Expressive"]
    directness: Literal["Indirect", "Balanced", "Direct", "Blunt"]
    typo_rate: Literal["None", "Low", "Moderate", "High"]
    warmth: Literal["Cool", "Neutral", "Friendly", "Warm"]


class PreferenceItem(BaseModel):
    value: str
    confidence: Literal["High", "Medium", "Low"]
    implicit: bool = True  # True = revealed implicitly in chat, False = stated directly


class PreferenceProfile(BaseModel):
    food: list[PreferenceItem] = Field(default_factory=list)
    activities: list[PreferenceItem] = Field(default_factory=list)
    social: list[PreferenceItem] = Field(default_factory=list)
    # Domain-specific preferences (e.g., trail difficulty for recreational)
    domain_specific: list[PreferenceItem] = Field(default_factory=list)


class PreferenceHistoryEvent(BaseModel):
    """Records a preference change over time — ground truth for Q8."""
    domain: str                     # e.g., "activities", "food"
    attribute: str                  # e.g., "hiking_difficulty"
    old_value: str
    new_value: str
    changed_at_session: int         # session ordinal (1-indexed)
    trigger: str                    # what caused the change (e.g., "Mike invited her")


class RelationshipEdge(BaseModel):
    """Directed relationship from persona_a to persona_b — ground truth for Q7."""
    persona_a_id: str
    persona_b_id: str
    relationship_type: str          # e.g., "childhood_friend", "cousin", "coworker"
    closeness: Literal["High", "Medium", "Low"]
    sentiment: Literal["positive", "neutral", "mixed", "tense"]
    history_summary: str            # 1-2 sentence shared history (Q7 ground truth)
    shared_events: list[str]        # memorable shared events (Q7 follow-on)


class GroupNorm(BaseModel):
    """A stated group habit — may or may not be truly universal. Ground truth for Q6."""
    norm_text: str                  # how the norm is phrased in chat (e.g., "we always do pizza")
    truly_universal: bool           # False = a consensus trap
    dissenters: list[str]           # persona_ids who don't actually share this norm


class Persona(BaseModel):
    persona_id: str
    display_name: str               # used in chat messages (e.g., "Mike")
    age: int
    gender: str
    background: str                 # 2-3 sentence bio
    big_five: BigFiveProfile
    communication_profile: CommunicationProfile
    preferences: PreferenceProfile
    preference_history: list[PreferenceHistoryEvent] = Field(default_factory=list)
    speaking_quirks: list[str]      # e.g., ["uses 'tbh' often", "never uses full stops"]


class EgoNetwork(BaseModel):
    network_id: str
    group_name: str                 # e.g., "Ridgeline Hikers"
    group_type: GroupType
    group_size: int
    seed: int
    personas: list[Persona]
    edges: list[RelationshipEdge]
    group_norms: list[GroupNorm]    # group habits with explicit universality flags
    metadata: dict = Field(default_factory=dict)
