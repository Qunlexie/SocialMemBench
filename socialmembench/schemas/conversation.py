"""Conversation schemas for SocialMemBench Stage 2."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChallengeType(str, Enum):
    IMPLICIT_PREFERENCE = "implicit_preference"     # preference reveal without direct statement → Q1/Q3
    CROSS_REFERENCE = "cross_reference"             # speaker references another member's preference → Q5
    CONSENSUS_TRAP = "consensus_trap"               # group decision ≠ individual preference → Q2/Q6
    THEORY_OF_MIND = "theory_of_mind"               # A relays what B told them about C → Q5
    TEMPORAL_SHIFT = "temporal_shift"               # preference contradicts earlier statement → Q8
    FALSE_ATTRIBUTION_SEED = "false_attribution_seed"  # planted to test contamination → Q4
    RELATIONAL_DISCLOSURE = "relational_disclosure"  # reveals relationship edge info → Q7
    RELATIONAL_GRAPH = "relational_graph"           # reveals cross-member connection structure → Q7 / Condition C


class PlantedChallenge(BaseModel):
    """
    Ground-truth record of a deliberately planted memory challenge.
    Stripped from the released dataset — used only for QA generation.
    """
    challenge_id: str
    challenge_type: ChallengeType
    subject_persona_id: str         # whose info is being revealed
    speaker_persona_id: str         # who is saying it (may differ for Q5/ToM)
    fact_attribute: str             # e.g., "trail_difficulty"
    fact_value: str                 # e.g., "dislikes_steep"
    evidence_span: str              # exact quote from the message
    implicitness_level: int         # 1=explicit, 2=implicit, 3=very implicit
    session_index: int
    turn_index: int


class ConversationTurn(BaseModel):
    turn_id: str
    session_id: str
    speaker_persona_id: str
    speaker_display_name: str
    timestamp_label: str            # e.g., "Jan 6, 11:23am"
    timestamp: Optional[str] = None # ISO 8601 datetime, e.g., "2025-01-06T11:23:00"
    message: str
    message_index: int              # sequential within session
    planted_challenges: list[PlantedChallenge] = Field(default_factory=list)
    reply_to_turn_id: Optional[str] = None


class ConversationSession(BaseModel):
    session_id: str
    network_id: str
    session_index: int              # ordinal position (1-indexed)
    topic: str                      # session topic (e.g., "planning the weekend hike")
    date_label: str                 # e.g., "Session 3, Monday March 17, 2025 5:47pm"
    date: Optional[str] = None      # ISO 8601 date, e.g., "2025-03-17"
    turns: list[ConversationTurn]
    prior_session_summary: Optional[str] = None  # rolling summary fed to generator
    critic_scores: Optional[dict] = None          # from Generator-Critic loop
    generation_attempts: int = 1


class ConversationCorpus(BaseModel):
    network_id: str
    start_date: Optional[str] = None  # ISO 8601 date of Session 1, e.g., "2025-01-06"
    sessions: list[ConversationSession]
    total_turns: int
    # Flat index of all planted challenges across all sessions — used by QA generator
    planted_challenge_index: list[PlantedChallenge] = Field(default_factory=list)

    def build_challenge_index(self) -> None:
        """Populate planted_challenge_index from all sessions/turns."""
        index = []
        for session in self.sessions:
            for turn in session.turns:
                index.extend(turn.planted_challenges)
        self.planted_challenge_index = index
        self.total_turns = sum(len(s.turns) for s in self.sessions)

    def get_turn_by_id(self, turn_id: str) -> Optional[ConversationTurn]:
        for session in self.sessions:
            for turn in session.turns:
                if turn.turn_id == turn_id:
                    return turn
        return None

    def render_plain_text(self) -> str:
        """Render the full corpus in WhatsApp-style plain text (no metadata)."""
        lines = []
        for session in self.sessions:
            lines.append(f"\n--- {session.date_label} ---")
            for turn in session.turns:
                ts = turn.timestamp_label
                lines.append(f"[{ts}] {turn.speaker_display_name}: {turn.message}")
        return "\n".join(lines)
