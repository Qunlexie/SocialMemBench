"""
Data bridge: converts SocialMemBench data formats to eval pipeline formats.

SocialMemBench stores:
  data/conversations/{network_id}.json  — ConversationCorpus (sessions + turns)
  data/qa/{network_id}.jsonl            — QAPair objects

This module converts those into:
  Dataset        — one GroupChatDay per session (for adapters)
  List[QAItem]   — for answerer + evaluator
"""
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from eval.core.data_models import (
    Dataset,
    GroupChatDay,
    GroupChatMessage,
    QAItem,
)


def load_corpus_as_dataset(network_id: str, data_dir: Path) -> Dataset:
    """
    Load a conversation corpus JSON and return a Dataset.

    Each session becomes a GroupChatDay (date = session date or index label).
    All turns in a session go into a single group keyed by network_id.

    Args:
        network_id: e.g. "grp_1a2b3c4d"
        data_dir: root data/ directory

    Returns:
        Dataset with one GroupChatDay per session
    """
    corpus_path = data_dir / "conversations" / f"{network_id}.json"
    if not corpus_path.exists():
        raise FileNotFoundError(f"Conversation corpus not found: {corpus_path}")

    with open(corpus_path, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    days: List[GroupChatDay] = []

    for session in corpus["sessions"]:
        session_index = session["session_index"]
        # Use ISO date if present, otherwise synthesize from session index
        date_str = session.get("date") or session.get("date_label") or f"session-{session_index:02d}"

        messages: List[GroupChatMessage] = []
        for turn in session["turns"]:
            raw_ts = turn.get("timestamp")
            if raw_ts:
                try:
                    ts = datetime.fromisoformat(raw_ts)
                except ValueError:
                    ts = datetime.min
            else:
                ts = datetime.min

            messages.append(
                GroupChatMessage(
                    speaker=turn["speaker_display_name"],
                    content=turn["message"],
                    timestamp=ts,
                    group=network_id,
                    date=date_str,
                    metadata={
                        "turn_id": turn.get("turn_id", ""),
                        "session_index": session_index,
                        "speaker_persona_id": turn.get("speaker_persona_id", ""),
                    },
                )
            )

        days.append(
            GroupChatDay(
                date=date_str,
                groups={network_id: messages},
                metadata={
                    "session_index": session_index,
                    "topic": session.get("topic", ""),
                    "session_id": session.get("session_id", ""),
                },
            )
        )

    return Dataset(
        name=network_id,
        days=days,
        metadata={
            "network_id": network_id,
            "total_turns": corpus.get("total_turns", 0),
        },
    )


def load_qa_pairs(
    network_id: str,
    data_dir: Path,
    query_types: Optional[List[str]] = None,
) -> List[QAItem]:
    """
    Load QA pairs from JSONL and return as QAItem list.

    Args:
        network_id: e.g. "grp_1a2b3c4d"
        data_dir: root data/ directory
        query_types: optional filter, e.g. ["Q1", "Q4"]. None = all.

    Returns:
        List of QAItem objects ready for the answerer
    """
    qa_path = data_dir / "qa" / f"{network_id}.jsonl"
    if not qa_path.exists():
        raise FileNotFoundError(f"QA file not found: {qa_path}")

    items: List[QAItem] = []

    with open(qa_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            pair = json.loads(line)

            # Filter by query type if requested
            if query_types and pair.get("query_type") not in query_types:
                continue

            # Map answer_format → question_type for the answerer
            answer_format = pair.get("answer_format", "long_form")
            if answer_format == "multiple_choice":
                question_type = "multiple_choice"
            else:
                question_type = "open_ended"

            # Build options list for MC (e.g. ["A. Maya", "B. Sam", ...])
            options = pair.get("options")
            if options and answer_format == "multiple_choice":
                letters = ["A", "B", "C", "D"]
                if isinstance(options, dict):
                    # QA JSONL stores options as {'A': 'Jordan', 'B': 'Maya', ...}
                    # Convert to ["A. Jordan", "B. Maya", ...] preserving letter order
                    formatted_options = []
                    for letter in letters:
                        if letter in options:
                            formatted_options.append(f"{letter}. {options[letter]}")
                    options = formatted_options
                elif isinstance(options, list):
                    # Options may already be pre-formatted or may be plain names
                    # Ensure format "A. Name", "B. Name", etc.
                    formatted_options = []
                    for i, opt in enumerate(options[:4]):
                        if len(opt) >= 3 and opt[0] in letters and opt[1] in ".):":
                            formatted_options.append(opt)
                        else:
                            prefix = letters[i] if i < len(letters) else str(i + 1)
                            formatted_options.append(f"{prefix}. {opt}")
                    options = formatted_options

            # golden_answer: use correct_option for MC, full answer for OE
            correct_option = pair.get("correct_option")
            golden_answer = pair.get("answer", "")
            if question_type == "multiple_choice" and correct_option:
                golden_answer = correct_option.upper()

            items.append(
                QAItem(
                    question_id=pair["qa_id"],
                    question=pair["question"],
                    answer=golden_answer,
                    question_type=question_type,
                    options=options,
                    correct_option=correct_option,
                    metadata={
                        "query_type": pair.get("query_type", ""),
                        "difficulty": pair.get("difficulty", ""),
                        "network_id": network_id,
                        "source_challenge_id": pair.get("source_challenge_id", ""),
                        "full_answer": pair.get("answer", ""),
                    },
                )
            )

    return items
