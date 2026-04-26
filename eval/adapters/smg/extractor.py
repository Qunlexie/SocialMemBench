"""
SMG extractor: conversation session → structured social signals.

Extraction is fully decoupled from evaluation. The LLM reads a session and
extracts social signals generically — no knowledge of QA pairs, planted
challenges, or query types. Whatever is in the conversation gets extracted.

Attribution invariant (never violated):
  - speaker_id is ALWAYS set from the source data field, before LLM runs
  - subject is LLM-inferred (who the fact is ABOUT — may differ from speaker)
  - if subject is ambiguous, default to speaker (self-disclosure assumption)

Extraction unit: one session at a time (full session text to LLM).
This gives more context than per-turn extraction and reduces API calls.

Prior context (session 2+):
  A summary of already-extracted facts is passed to the extractor so it can
  identify temporal shifts — cases where the current session contradicts or
  updates a prior belief. This does NOT expose any QA or evaluation data;
  it is purely the graph's own accumulated knowledge passed back to the extractor.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

SYSTEM_PROMPT = """You extract social memory signals from group chat conversations.
Your output powers a knowledge graph. Be precise and grounded — only extract
what is clearly evidenced in the text. Return valid JSON only."""

EXTRACTION_PROMPT = """Group members: {member_names}

{prior_context_section}Session {session} conversation:
{session_text}

Extract all social signals present in this conversation. Return JSON with these fields:

{{
  "facts": [
    {{
      "subject": "<member name — who this fact is ABOUT>",
      "speaker": "<member name — who said/revealed this>",
      "domain": "<2-4 word snake_case label, e.g. trail_difficulty, food_preference, meeting_time>",
      "value": "<the preference, belief, or state in one sentence>",
      "implicitness": <1|2|3>,
      "evidence_quote": "<verbatim words from the conversation, max 100 chars>",
      "supersedes_prior": <true|false>
    }}
  ],
  "knows_about": [
    {{
      "knower": "<member name — who demonstrated prior knowledge>",
      "subject": "<member name — who the knowledge is about>",
      "domain": "<domain>",
      "evidence_quote": "<verbatim words showing they already knew, max 100 chars>"
    }}
  ],
  "norms": [
    {{
      "speaker": "<member name — who stated this norm>",
      "domain": "<domain>",
      "value": "<what the norm is, one sentence>"
    }}
  ],
  "dissents": [
    {{
      "speaker": "<member name — who dissented>",
      "norm_domain": "<domain of norm being dissented from>",
      "signal": "<explicit_reject|qualifier|silence|topic_change>",
      "evidence_quote": "<verbatim words or describe the silence/deflection>"
    }}
  ],
  "relationships": [
    {{
      "persona_a": "<member name>",
      "persona_b": "<member name>",
      "description": "<one sentence describing their relationship or shared history>"
    }}
  ]
}}

Definitions:
- implicitness 1: stated directly ("I hate steep trails")
- implicitness 2: implied through complaint, behavior, or reaction ("my knees still haven't forgiven that climb")
- implicitness 3: revealed through silence, deflection, or changing the subject
- knows_about: only when a speaker's phrasing implies they ALREADY knew something before this session (e.g. "didn't you say you hate steep ones?", referencing a prior preference unprompted)
- subject must be a name from the member list
- speaker must be a name from the member list
- only include what is grounded in this session's text
- supersedes_prior: set to true if this fact UPDATES OR CONTRADICTS something in the prior knowledge (a temporal shift). Set to false if it is new or consistent with prior knowledge.

IMPORTANT — implicit signals to capture:
- Avoidance: "I'll have the [alternative]" when a specific item is offered → aversion to that item
- Asking for options: "is there anything I can eat?" → dietary restriction
- Deflection: changing the subject when a topic comes up → discomfort with it
- Role changes: if prior knowledge shows someone had a role and they are now absent from it → note the shift
- Lifestyle changes: "these days", "not anymore", "I'm off X now", "used to but" → temporal shift, set supersedes_prior=true

Return ONLY valid JSON. Empty arrays are fine if nothing is present."""


def _format_prior_context(prior_facts: List[Dict]) -> str:
    """Format prior graph facts as a compact summary for the extractor."""
    if not prior_facts:
        return ""
    lines = ["Prior knowledge from earlier sessions (use this to identify temporal shifts):"]
    for pf in prior_facts:
        lines.append(f"  - {pf['subject']}: [{pf['domain']}] {pf['value']} (session {pf['session']})")
    return "\n".join(lines) + "\n\n"


def _format_session(turns: List[Dict[str, Any]]) -> str:
    """Format turns as plain chat transcript."""
    lines = []
    for t in turns:
        lines.append(f"[{t['speaker']}] {t['message']}")
    return "\n".join(lines)


def _parse_response(text: str) -> Dict[str, List]:
    """Parse LLM JSON, return empty structure on failure."""
    empty = {
        "facts": [], "knows_about": [],
        "norms": [], "dissents": [], "relationships": []
    }
    try:
        text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
        data = json.loads(text)
        for key in empty:
            if key not in data or not isinstance(data[key], list):
                data[key] = []
        return data
    except Exception:
        return empty


async def extract_session(
    llm_client,
    turns: List[Dict[str, Any]],
    member_names: List[str],
    session: int,
    prior_facts: Optional[List[Dict]] = None,
    extraction_model: str = "gpt-4o-mini",
) -> Dict[str, List]:
    """
    Extract all social signals from one session.

    turns: list of {speaker, speaker_id, message}
    prior_facts: list of {subject, domain, value, session} from earlier sessions.
                 Passed so the LLM can detect temporal shifts. Does NOT contain
                 any QA or evaluation data — only what the graph already holds.
    Returns raw extraction dict — graph insertion handled by smg_adapter.
    """
    session_text = _format_session(turns)
    prior_context_section = _format_prior_context(prior_facts or [])
    prompt = EXTRACTION_PROMPT.format(
        member_names=", ".join(member_names),
        prior_context_section=prior_context_section,
        session=session,
        session_text=session_text,
    )

    response = await llm_client.chat.completions.create(
        model=extraction_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content or "{}"
    return _parse_response(text)
