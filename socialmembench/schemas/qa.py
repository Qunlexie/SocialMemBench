"""QA pair schemas for SocialMemBench Stage 3."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

QueryType = Literal["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"]
AnswerFormat = Literal["multiple_choice", "short_answer", "long_form"]

# Default answer format per query type
QUERY_TYPE_FORMATS: dict[str, AnswerFormat] = {
    "Q1": "long_form",          # nuanced preference recall
    "Q2": "multiple_choice",    # who dissented? — single-person answer
    "Q3": "long_form",          # must enumerate all personas
    "Q4": "multiple_choice",    # who said X? — clearest MC candidate
    "Q5": "long_form",          # two-part: what preference + who revealed it
    "Q6": "multiple_choice",    # who isn't actually on board? — single-person answer
    "Q7": "short_answer",       # relationship type/description as short phrase
    "Q8": "long_form",          # temporal narrative + temporal_anchors
}

QUERY_TYPE_LABELS: dict[str, str] = {
    "Q1": "single_contact_recall",
    "Q2": "group_decision_recall",
    "Q3": "multi_contact_aggregation",
    "Q4": "contamination_probe",
    "Q5": "theory_of_mind_reference",
    "Q6": "norm_vs_individual",
    "Q7": "relational_edge_query",
    "Q8": "temporal_preference_evolution",
}


class EvidenceAnchor(BaseModel):
    """Points to a specific turn in the corpus that supports the answer."""
    session_index: int
    turn_id: str
    speaker_display_name: str
    message_excerpt: str            # exact quote (for verification)
    relevance: str                  # brief note on why this is evidence


class QAPair(BaseModel):
    qa_id: str
    network_id: str
    group_id: str                   # same as network_id, kept for EverMemBench compatibility
    query_type: QueryType
    query_type_label: str
    difficulty: Literal["easy", "medium", "hard"]
    question: str
    answer: str                     # ground truth answer
    # Evidence anchoring — every answer must be derivable from these turns only
    evidence_anchors: list[EvidenceAnchor]
    # Answer format fields
    answer_format: AnswerFormat = "long_form"
    options: Optional[dict[str, str]] = None     # MC only: {"A": "Jordan", "B": "Maya", ...}
    correct_option: Optional[str] = None         # MC: letter key; short_answer: canonical short value
    # Optional fields for specific query types
    contamination_foil: Optional[str] = None    # Q4: the plausible-but-wrong attribution
    temporal_anchors: Optional[list[dict]] = None  # Q8: [{session_index, value}]
    # QC pipeline results
    qc_phase1_score: Optional[float] = None
    qc_phase2_grounded: Optional[bool] = None
    qc_phase3_flagged: Optional[bool] = None
    qc_phase3_flag_reason: Optional[str] = None
    # Provenance
    source_challenge_id: Optional[str] = None  # which PlantedChallenge generated this
    generation_seed: int = 0
    metadata: dict = Field(default_factory=dict)
