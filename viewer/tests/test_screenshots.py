"""Playwright screenshot tests for SocialMemBench Viewer.

Verifies the UI looks correct by:
1. Seeding fixture data into a temp data directory
2. Starting the server against that fixture data
3. Taking screenshots of all views
4. Asserting key DOM elements are present and visible
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright, expect

# ── Paths ──────────────────────────────────────────────────────────────────────
VIEWER_DIR = Path(__file__).parent.parent
REPO_ROOT  = VIEWER_DIR.parent
SHOTS_DIR  = Path(__file__).parent / "screenshots"

# ── Fixture data ───────────────────────────────────────────────────────────────
NETWORK_ID = "grp_fixture01"

NETWORK = {
    "network_id": NETWORK_ID,
    "group_name": "Ridgeline Hikers",
    "group_type": "recreational",
    "group_size": 4,
    "seed": 42,
    "personas": [
        {
            "persona_id": "p_alice",
            "display_name": "Alice",
            "age": 32,
            "gender": "female",
            "occupation": "graphic designer",
            "background": "Alice grew up in Colorado and has been hiking since she was a kid. She loves the outdoors and brings homemade trail mix every trip.",
            "skills_list": [{"skill": "route planning", "proficiency": "strong"}],
            "big_five": {"openness":"High","conscientiousness":"Medium","extraversion":"High","agreeableness":"High","neuroticism":"Low"},
            "communication_profile": {"formality":"Casual","verbosity":"Concise","emoji_use":"Moderate","humor":"Playful","directness":"Direct","typo_rate":"Low","warmth":"Warm"},
            "preferences": {
                "food": [{"value": "loves trail mix","confidence":"High","implicit":False}],
                "activities": [{"value": "prefers flat trails","confidence":"High","implicit":True}],
                "social": [],
                "domain_specific": []
            },
            "preference_history": [],
            "speaking_quirks": ["uses 'tbh' often", "lots of exclamation marks"]
        },
        {
            "persona_id": "p_mike",
            "display_name": "Mike",
            "age": 35,
            "gender": "male",
            "occupation": "software engineer",
            "background": "Mike moved to the city three years ago and joined the hiking group to meet people. He secretly dislikes steep trails but doesn't want to be the one to say it.",
            "skills_list": [{"skill": "navigation", "proficiency": "medium"}],
            "big_five": {"openness":"Medium","conscientiousness":"High","extraversion":"Low","agreeableness":"Medium","neuroticism":"Medium"},
            "communication_profile": {"formality":"Casual","verbosity":"Terse","emoji_use":"Rare","humor":"Dry","directness":"Indirect","typo_rate":"None","warmth":"Neutral"},
            "preferences": {
                "food": [{"value": "avoids spicy food","confidence":"High","implicit":True}],
                "activities": [{"value": "dislikes steep trails","confidence":"High","implicit":True}],
                "social": [],
                "domain_specific": []
            },
            "preference_history": [
                {"domain":"activities","attribute":"hiking_difficulty","old_value":"neutral","new_value":"dislikes_steep","changed_at_session":2,"trigger":"twisted ankle on Devil's Backbone"}
            ],
            "speaking_quirks": ["very brief replies", "uses ellipses"]
        },
        {
            "persona_id": "p_sarah",
            "display_name": "Sarah",
            "age": 28,
            "gender": "female",
            "occupation": "teacher",
            "background": "Sarah is the most experienced hiker in the group. She once completed the Pacific Crest Trail section through Oregon.",
            "skills_list": [{"skill": "wilderness first aid", "proficiency": "strong"}],
            "big_five": {"openness":"High","conscientiousness":"High","extraversion":"Medium","agreeableness":"High","neuroticism":"Low"},
            "communication_profile": {"formality":"Semi-formal","verbosity":"Verbose","emoji_use":"Moderate","humor":"Expressive","directness":"Balanced","typo_rate":"Low","warmth":"Friendly"},
            "preferences": {
                "food": [{"value": "vegetarian","confidence":"High","implicit":False}],
                "activities": [{"value": "loves challenging peaks","confidence":"High","implicit":False}],
                "social": [],
                "domain_specific": []
            },
            "preference_history": [],
            "speaking_quirks": ["writes in complete sentences", "includes fun facts"]
        },
        {
            "persona_id": "p_leo",
            "display_name": "Leo",
            "age": 30,
            "gender": "male",
            "occupation": "photographer",
            "background": "Leo joined the group primarily for photography opportunities. He often lags behind to get the perfect shot.",
            "skills_list": [{"skill": "landscape photography", "proficiency": "strong"}],
            "big_five": {"openness":"High","conscientiousness":"Low","extraversion":"Medium","agreeableness":"High","neuroticism":"Low"},
            "communication_profile": {"formality":"Casual","verbosity":"Concise","emoji_use":"Frequent","humor":"Minimal","directness":"Balanced","typo_rate":"Moderate","warmth":"Friendly"},
            "preferences": {
                "food": [],
                "activities": [{"value": "prefers scenic routes over speed","confidence":"High","implicit":True}],
                "social": [],
                "domain_specific": []
            },
            "preference_history": [],
            "speaking_quirks": ["sends lots of photo reactions 📸", "trails off mid-sentence"]
        }
    ],
    "edges": [
        {
            "persona_a_id": "p_alice",
            "persona_b_id": "p_mike",
            "relationship_type": "childhood_friends",
            "closeness": "High",
            "sentiment": "positive",
            "history_summary": "Alice and Mike grew up on the same street in Denver and have been hiking together since high school.",
            "shared_events": ["First summit attempt together", "Rescue during a storm on Mt. Evans"]
        },
        {
            "persona_a_id": "p_alice",
            "persona_b_id": "p_sarah",
            "relationship_type": "acquaintances",
            "closeness": "Medium",
            "sentiment": "positive",
            "history_summary": "Alice met Sarah through the hiking club two years ago. They get along well but don't hang out outside of hikes.",
            "shared_events": ["Completed the Flatirons traverse together"]
        },
        {
            "persona_a_id": "p_sarah",
            "persona_b_id": "p_leo",
            "relationship_type": "coworkers",
            "closeness": "Medium",
            "sentiment": "mixed",
            "history_summary": "Sarah and Leo teach at the same school. Leo sometimes shows up late for hikes, which frustrates Sarah.",
            "shared_events": ["School camping trip last summer"]
        },
        {
            "persona_a_id": "p_mike",
            "persona_b_id": "p_leo",
            "relationship_type": "casual_friends",
            "closeness": "Low",
            "sentiment": "neutral",
            "history_summary": "Mike and Leo met through the group. They rarely talk outside of hikes.",
            "shared_events": []
        }
    ],
    "group_norms": [
        {
            "norm_text": "we always bring enough food to share",
            "truly_universal": True,
            "dissenters": []
        },
        {
            "norm_text": "we always vote on the trail difficulty together",
            "truly_universal": False,
            "dissenters": ["p_sarah"]
        }
    ],
    "metadata": {}
}

CONVERSATIONS = {
    "network_id": NETWORK_ID,
    "start_date": "2025-03-17",
    "total_turns": 14,
    "sessions": [
        {
            "session_id": f"{NETWORK_ID}_s01",
            "network_id": NETWORK_ID,
            "session_index": 1,
            "topic": "planning the weekend hike",
            "date_label": "Session 1 · Monday March 17, 2025 5:47pm",
            "date": "2025-03-17",
            "prior_session_summary": None,
            "critic_scores": None,
            "generation_attempts": 1,
            "turns": [
                {
                    "turn_id": f"{NETWORK_ID}_s01_t001",
                    "session_id": f"{NETWORK_ID}_s01",
                    "speaker_persona_id": "p_alice",
                    "speaker_display_name": "Alice",
                    "timestamp_label": "Mar 17, 5:47pm",
                    "timestamp": "2025-03-17T17:47:00",
                    "message": "ok so are we doing the Flatirons loop again this Saturday or something new? tbh I'm game for anything!",
                    "message_index": 0,
                    "reply_to_turn_id": None,
                    "planted_challenges": []
                },
                {
                    "turn_id": f"{NETWORK_ID}_s01_t002",
                    "session_id": f"{NETWORK_ID}_s01",
                    "speaker_persona_id": "p_mike",
                    "speaker_display_name": "Mike",
                    "timestamp_label": "Mar 17, 5:52pm",
                    "timestamp": "2025-03-17T17:52:00",
                    "message": "the loop is fine i guess...",
                    "message_index": 1,
                    "reply_to_turn_id": None,
                    "planted_challenges": [
                        {
                            "challenge_id": "ch_0001",
                            "challenge_type": "implicit_preference",
                            "subject_persona_id": "p_mike",
                            "speaker_persona_id": "p_mike",
                            "fact_attribute": "hiking_difficulty",
                            "fact_value": "unenthusiastic_about_challenging_hike",
                            "evidence_span": "the loop is fine i guess...",
                            "implicitness_level": 2,
                            "session_index": 1,
                            "turn_index": 1
                        }
                    ]
                },
                {
                    "turn_id": f"{NETWORK_ID}_s01_t003",
                    "session_id": f"{NETWORK_ID}_s01",
                    "speaker_persona_id": "p_sarah",
                    "speaker_display_name": "Sarah",
                    "timestamp_label": "Mar 17, 5:55pm",
                    "timestamp": "2025-03-17T17:55:00",
                    "message": "I vote we try Devil's Backbone! The elevation gain is actually amazing and the views are unreal. Fun fact: it's a designated natural landmark 🏔️",
                    "message_index": 2,
                    "reply_to_turn_id": None,
                    "planted_challenges": []
                },
                {
                    "turn_id": f"{NETWORK_ID}_s01_t004",
                    "session_id": f"{NETWORK_ID}_s01",
                    "speaker_persona_id": "p_leo",
                    "speaker_display_name": "Leo",
                    "timestamp_label": "Mar 17, 5:58pm",
                    "timestamp": "2025-03-17T17:58:00",
                    "message": "sounds good 📸 hope the light is good in the afternoon",
                    "message_index": 3,
                    "reply_to_turn_id": None,
                    "planted_challenges": []
                },
                {
                    "turn_id": f"{NETWORK_ID}_s01_t005",
                    "session_id": f"{NETWORK_ID}_s01",
                    "speaker_persona_id": "p_alice",
                    "speaker_display_name": "Alice",
                    "timestamp_label": "Mar 17, 6:01pm",
                    "timestamp": "2025-03-17T18:01:00",
                    "message": "ok Devil's Backbone it is then! I'll bring my famous trail mix!!",
                    "message_index": 4,
                    "reply_to_turn_id": None,
                    "planted_challenges": []
                },
                {
                    "turn_id": f"{NETWORK_ID}_s01_t006",
                    "session_id": f"{NETWORK_ID}_s01",
                    "speaker_persona_id": "p_mike",
                    "speaker_display_name": "Mike",
                    "timestamp_label": "Mar 17, 6:04pm",
                    "timestamp": "2025-03-17T18:04:00",
                    "message": "sure. what time?",
                    "message_index": 5,
                    "reply_to_turn_id": None,
                    "planted_challenges": []
                },
                {
                    "turn_id": f"{NETWORK_ID}_s01_t007",
                    "session_id": f"{NETWORK_ID}_s01",
                    "speaker_persona_id": "p_sarah",
                    "speaker_display_name": "Sarah",
                    "timestamp_label": "Mar 17, 6:06pm",
                    "timestamp": "2025-03-17T18:06:00",
                    "message": "7am trailhead? Golden hour lighting for Leo 😄",
                    "message_index": 6,
                    "reply_to_turn_id": None,
                    "planted_challenges": []
                }
            ]
        },
        {
            "session_id": f"{NETWORK_ID}_s02",
            "network_id": NETWORK_ID,
            "session_index": 2,
            "topic": "post-hike debrief",
            "date_label": "Session 2 · Sunday March 23, 2025 3:15pm",
            "date": "2025-03-23",
            "prior_session_summary": "The group planned a Saturday hike to Devil's Backbone.",
            "critic_scores": None,
            "generation_attempts": 1,
            "turns": [
                {
                    "turn_id": f"{NETWORK_ID}_s02_t001",
                    "session_id": f"{NETWORK_ID}_s02",
                    "speaker_persona_id": "p_alice",
                    "speaker_display_name": "Alice",
                    "timestamp_label": "Mar 23, 3:15pm",
                    "timestamp": "2025-03-23T15:15:00",
                    "message": "OMG that was so good!! My legs are dead but totally worth it tbh 😭",
                    "message_index": 0,
                    "reply_to_turn_id": None,
                    "planted_challenges": []
                },
                {
                    "turn_id": f"{NETWORK_ID}_s02_t002",
                    "session_id": f"{NETWORK_ID}_s02",
                    "speaker_persona_id": "p_sarah",
                    "speaker_display_name": "Sarah",
                    "timestamp_label": "Mar 23, 3:17pm",
                    "timestamp": "2025-03-23T15:17:00",
                    "message": "Mike you were super quiet the whole second half. You alright? I noticed you were favouring your left ankle on the way down.",
                    "message_index": 1,
                    "reply_to_turn_id": None,
                    "planted_challenges": [
                        {
                            "challenge_id": "ch_0002",
                            "challenge_type": "theory_of_mind",
                            "subject_persona_id": "p_mike",
                            "speaker_persona_id": "p_sarah",
                            "fact_attribute": "ankle_injury",
                            "fact_value": "twisted_ankle_on_steep_descent",
                            "evidence_span": "I noticed you were favouring your left ankle on the way down",
                            "implicitness_level": 2,
                            "session_index": 2,
                            "turn_index": 1
                        }
                    ]
                },
                {
                    "turn_id": f"{NETWORK_ID}_s02_t003",
                    "session_id": f"{NETWORK_ID}_s02",
                    "speaker_persona_id": "p_mike",
                    "speaker_display_name": "Mike",
                    "timestamp_label": "Mar 23, 3:21pm",
                    "timestamp": "2025-03-23T15:21:00",
                    "message": "it's fine. maybe we do something a bit flatter next time",
                    "message_index": 2,
                    "reply_to_turn_id": None,
                    "planted_challenges": [
                        {
                            "challenge_id": "ch_0003",
                            "challenge_type": "temporal_shift",
                            "subject_persona_id": "p_mike",
                            "speaker_persona_id": "p_mike",
                            "fact_attribute": "hiking_difficulty_preference",
                            "fact_value": "now_prefers_flat_trails",
                            "evidence_span": "maybe we do something a bit flatter next time",
                            "implicitness_level": 2,
                            "session_index": 2,
                            "turn_index": 2
                        }
                    ]
                },
                {
                    "turn_id": f"{NETWORK_ID}_s02_t004",
                    "session_id": f"{NETWORK_ID}_s02",
                    "speaker_persona_id": "p_leo",
                    "speaker_display_name": "Leo",
                    "timestamp_label": "Mar 23, 3:24pm",
                    "timestamp": "2025-03-23T15:24:00",
                    "message": "got some 🔥 shots btw. the ridge at golden hour was perfect",
                    "message_index": 3,
                    "reply_to_turn_id": None,
                    "planted_challenges": []
                },
                {
                    "turn_id": f"{NETWORK_ID}_s02_t005",
                    "session_id": f"{NETWORK_ID}_s02",
                    "speaker_persona_id": "p_alice",
                    "speaker_display_name": "Alice",
                    "timestamp_label": "Mar 23, 3:26pm",
                    "timestamp": "2025-03-23T15:26:00",
                    "message": "Leo!! Please share!! 👀 And yeah Mike let's do something easier — maybe Bear Creek trail? It's gorgeous and flat tbh",
                    "message_index": 4,
                    "reply_to_turn_id": None,
                    "planted_challenges": []
                },
                {
                    "turn_id": f"{NETWORK_ID}_s02_t006",
                    "session_id": f"{NETWORK_ID}_s02",
                    "speaker_persona_id": "p_mike",
                    "speaker_display_name": "Mike",
                    "timestamp_label": "Mar 23, 3:29pm",
                    "timestamp": "2025-03-23T15:29:00",
                    "message": "yeah that works",
                    "message_index": 5,
                    "reply_to_turn_id": None,
                    "planted_challenges": []
                },
                {
                    "turn_id": f"{NETWORK_ID}_s02_t007",
                    "session_id": f"{NETWORK_ID}_s02",
                    "speaker_persona_id": "p_sarah",
                    "speaker_display_name": "Sarah",
                    "timestamp_label": "Mar 23, 3:32pm",
                    "timestamp": "2025-03-23T15:32:00",
                    "message": "Bear Creek is fine but we should push ourselves more. I'll go either way though — you all vote!",
                    "message_index": 6,
                    "reply_to_turn_id": None,
                    "planted_challenges": [
                        {
                            "challenge_id": "ch_0004",
                            "challenge_type": "consensus_trap",
                            "subject_persona_id": "p_sarah",
                            "speaker_persona_id": "p_sarah",
                            "fact_attribute": "trail_difficulty_preference",
                            "fact_value": "disagrees_with_easy_trail_consensus",
                            "evidence_span": "Bear Creek is fine but we should push ourselves more",
                            "implicitness_level": 1,
                            "session_index": 2,
                            "turn_index": 6
                        }
                    ]
                }
            ]
        }
    ],
    "planted_challenge_index": []
}

QA_PAIRS = [
    {
        "qa_id": "Q1_fixture01",
        "network_id": NETWORK_ID,
        "group_id": NETWORK_ID,
        "query_type": "Q1",
        "query_type_label": "single_contact_recall",
        "difficulty": "medium",
        "question": "Based on the conversations, what is Mike's implicit preference regarding trail difficulty?",
        "answer": "Mike implicitly prefers flat or easy trails. This is revealed through his unenthusiastic response when the group chose Devil's Backbone ('the loop is fine i guess...'), and confirmed after the hike when he suggested 'maybe we do something a bit flatter next time', likely triggered by his ankle discomfort on the steep descent.",
        "evidence_anchors": [
            {
                "session_index": 1,
                "turn_id": f"{NETWORK_ID}_s01_t002",
                "speaker_display_name": "Mike",
                "message_excerpt": "the loop is fine i guess...",
                "relevance": "Lukewarm response implies reluctance about a challenging trail choice"
            },
            {
                "session_index": 2,
                "turn_id": f"{NETWORK_ID}_s02_t003",
                "speaker_display_name": "Mike",
                "message_excerpt": "maybe we do something a bit flatter next time",
                "relevance": "Direct (but understated) request for an easier trail after the hike"
            }
        ],
        "answer_format": "long_form",
        "options": None,
        "correct_option": None,
        "contamination_foil": None,
        "temporal_anchors": None,
        "qc_phase1_score": 0.87,
        "qc_phase2_grounded": True,
        "qc_phase3_flagged": False,
        "qc_phase3_flag_reason": None,
        "source_challenge_id": "ch_0001",
        "generation_seed": 42,
        "metadata": {}
    },
    {
        "qa_id": "Q2_fixture01",
        "network_id": NETWORK_ID,
        "group_id": NETWORK_ID,
        "query_type": "Q2",
        "query_type_label": "group_decision_recall",
        "difficulty": "easy",
        "question": "The group decided to hike Bear Creek trail next time. Who expressed reluctance about this decision?",
        "answer": "Sarah expressed reluctance. While she said she'd go along with the group's vote, she explicitly noted that the group 'should push ourselves more', signalling disagreement with the easier option.",
        "evidence_anchors": [
            {
                "session_index": 2,
                "turn_id": f"{NETWORK_ID}_s02_t007",
                "speaker_display_name": "Sarah",
                "message_excerpt": "Bear Creek is fine but we should push ourselves more",
                "relevance": "Sarah's 'but' construction signals disagreement despite outward compliance"
            }
        ],
        "answer_format": "multiple_choice",
        "options": {"A": "Alice", "B": "Mike", "C": "Sarah", "D": "Leo"},
        "correct_option": "C",
        "contamination_foil": None,
        "temporal_anchors": None,
        "qc_phase1_score": 0.94,
        "qc_phase2_grounded": True,
        "qc_phase3_flagged": False,
        "qc_phase3_flag_reason": None,
        "source_challenge_id": "ch_0004",
        "generation_seed": 42,
        "metadata": {}
    },
    {
        "qa_id": "Q5_fixture01",
        "network_id": NETWORK_ID,
        "group_id": NETWORK_ID,
        "query_type": "Q5",
        "query_type_label": "theory_of_mind_reference",
        "difficulty": "hard",
        "question": "Sarah revealed something about Mike's physical condition during the hike. What did she notice, and what does it suggest about his experience?",
        "answer": "Sarah noticed that Mike was 'favouring his left ankle on the way down', suggesting he had twisted or hurt his ankle during the steep descent of Devil's Backbone. This physical discomfort likely explains both his quietness during the second half and his subsequent request for a flatter trail.",
        "evidence_anchors": [
            {
                "session_index": 2,
                "turn_id": f"{NETWORK_ID}_s02_t002",
                "speaker_display_name": "Sarah",
                "message_excerpt": "I noticed you were favouring your left ankle on the way down",
                "relevance": "Sarah's observation reveals Mike's injury that Mike himself never disclosed"
            }
        ],
        "answer_format": "long_form",
        "options": None,
        "correct_option": None,
        "contamination_foil": None,
        "temporal_anchors": None,
        "qc_phase1_score": 0.79,
        "qc_phase2_grounded": True,
        "qc_phase3_flagged": False,
        "qc_phase3_flag_reason": None,
        "source_challenge_id": "ch_0002",
        "generation_seed": 42,
        "metadata": {}
    },
    {
        "qa_id": "Q8_fixture01",
        "network_id": NETWORK_ID,
        "group_id": NETWORK_ID,
        "query_type": "Q8",
        "query_type_label": "temporal_preference_evolution",
        "difficulty": "hard",
        "question": "How did Mike's stated preference for trail difficulty change across the two sessions?",
        "answer": "In Session 1, Mike was passive and unenthusiastic ('the loop is fine i guess...') — neither endorsing nor opposing the challenging Devil's Backbone choice. By Session 2, after the hike, he explicitly requested a flatter trail ('maybe we do something a bit flatter next time'). His preference shifted from passive non-resistance to active preference for easier terrain, likely triggered by an ankle injury sustained on the steep descent.",
        "evidence_anchors": [
            {
                "session_index": 1,
                "turn_id": f"{NETWORK_ID}_s01_t002",
                "speaker_display_name": "Mike",
                "message_excerpt": "the loop is fine i guess...",
                "relevance": "Session 1: passive, non-committal — no expressed preference for difficulty"
            },
            {
                "session_index": 2,
                "turn_id": f"{NETWORK_ID}_s02_t003",
                "speaker_display_name": "Mike",
                "message_excerpt": "maybe we do something a bit flatter next time",
                "relevance": "Session 2: active preference for flat trails emerged after hike"
            }
        ],
        "answer_format": "long_form",
        "options": None,
        "correct_option": None,
        "contamination_foil": None,
        "temporal_anchors": [
            {"session_index": 1, "value": "neutral / unenthusiastic"},
            {"session_index": 2, "value": "actively prefers flat trails"}
        ],
        "qc_phase1_score": 0.83,
        "qc_phase2_grounded": True,
        "qc_phase3_flagged": False,
        "qc_phase3_flag_reason": None,
        "source_challenge_id": "ch_0003",
        "generation_seed": 42,
        "metadata": {}
    }
]


def seed_fixture_data(data_dir: Path) -> None:
    """Write fixture data into data_dir."""
    (data_dir / "raw").mkdir(parents=True)
    (data_dir / "conversations").mkdir(parents=True)
    (data_dir / "qa").mkdir(parents=True)

    (data_dir / "raw" / f"{NETWORK_ID}.json").write_text(json.dumps(NETWORK, indent=2))
    (data_dir / "conversations" / f"{NETWORK_ID}.json").write_text(json.dumps(CONVERSATIONS, indent=2))

    qa_path = data_dir / "qa" / f"{NETWORK_ID}.jsonl"
    qa_path.write_text("\n".join(json.dumps(q) for q in QA_PAIRS))


def start_server(data_dir: Path, port: int = 8181):
    """Start the FastAPI server with a custom DATA_DIR override via env var."""
    env = os.environ.copy()
    env["SMB_DATA_DIR"] = str(data_dir)
    proc = subprocess.Popen(
        [sys.executable, str(VIEWER_DIR / "server.py"), "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for server to be ready
    for _ in range(20):
        time.sleep(0.5)
        try:
            import urllib.request
            urllib.request.urlopen(f"http://localhost:{port}/api/networks", timeout=1)
            break
        except Exception:
            pass
    return proc


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def server_and_data():
    import urllib.request

    SHOTS_DIR.mkdir(exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="smb_test_"))
    seed_fixture_data(tmp)

    PORT = 8181
    env = os.environ.copy()
    env["SMB_DATA_DIR"] = str(tmp)

    proc = subprocess.Popen(
        [sys.executable, str(VIEWER_DIR / "server.py"), "--port", str(PORT)],
        env=env,
        cwd=str(VIEWER_DIR),  # run from viewer/ so HERE is correct
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait up to 15s for server to be ready
    ready = False
    for _ in range(30):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://localhost:{PORT}/api/networks", timeout=1)
            ready = True
            break
        except Exception:
            continue

    if not ready:
        proc.terminate()
        stdout, stderr = proc.communicate(timeout=5)
        raise RuntimeError(
            f"Server failed to start.\nstdout: {stdout.decode()[:500]}\nstderr: {stderr.decode()[:500]}"
        )

    yield f"http://localhost:{PORT}"

    proc.terminate()
    proc.wait()
    shutil.rmtree(tmp, ignore_errors=True)


# ── Tests ──────────────────────────────────────────────────────────────────────

def take(page: Page, name: str):
    path = SHOTS_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  📸 {path}")
    return path


def test_01_landing(server_and_data, page: Page):
    """Landing page shows the sidebar and welcome state."""
    page.goto(server_and_data)
    page.wait_for_load_state("networkidle")

    take(page, "01_landing")

    # Header present
    assert page.locator(".header-title").is_visible()
    assert page.locator(".sidebar").is_visible()

    # At least one network listed
    assert page.locator(".network-item").count() >= 1

    # Welcome panel visible
    assert page.locator(".welcome").is_visible()


def test_01b_narrow_layout(server_and_data, page: Page):
    """The viewer keeps navigation and chat usable at a narrower viewport."""
    page.set_viewport_size({"width": 720, "height": 1180})
    page.goto(server_and_data)
    page.wait_for_load_state("networkidle")

    assert page.locator(".sidebar").is_visible()

    page.locator(".network-item").first.click()
    page.wait_for_selector(".message-bubble", timeout=5000)

    assert page.locator(".tab-bar").is_visible()
    assert page.locator(".session-list").is_visible()
    assert page.locator("#chat-container").is_visible()


def test_02_network_selected_chat(server_and_data, page: Page):
    """Clicking a network shows the chat view with message bubbles."""
    page.goto(server_and_data)
    page.wait_for_load_state("networkidle")

    page.locator(".network-item").first.click()
    page.wait_for_selector(".message-bubble", timeout=5000)

    take(page, "02_chat_view")

    # Network name updated
    assert page.locator("#network-name").is_visible()
    assert page.locator("#chat-overview").is_visible()

    # Multiple message bubbles
    assert page.locator(".message-bubble").count() > 5

    # Session headers
    assert page.locator(".session-header").count() >= 2

    # Challenge badge shown (Mike's message has planted_challenges)
    assert page.locator(".challenge-badge").count() >= 1

    # Speaker avatars
    assert page.locator(".msg-avatar:not(.spacer)").count() >= 4

    # Session switch updates the active list item and chat overview
    page.locator(".session-list-item").nth(1).click()
    page.wait_for_timeout(300)
    expect(page.locator(".session-list-item.active")).to_have_count(1)
    expect(page.locator("#chat-overview")).to_contain_text("Session 2")


def test_03_graph_view(server_and_data, page: Page):
    """Graph tab shows D3 SVG with nodes and edges."""
    page.goto(server_and_data)
    page.wait_for_load_state("networkidle")

    page.locator(".network-item").first.click()
    page.wait_for_selector(".message-bubble", timeout=5000)

    page.locator(".tab[data-tab='graph']").click()
    page.wait_for_selector("#graph-svg circle", timeout=6000)

    take(page, "03_graph_view")

    # Graph summary visible
    assert page.locator("#graph-summary").is_visible()

    # SVG with nodes
    assert page.locator("#graph-svg circle").count() >= 4

    # SVG with edges
    assert page.locator("#graph-svg line.link").count() >= 3

    # Detail panel empty state visible
    assert page.locator(".graph-detail").is_visible()


def test_04_graph_node_click(server_and_data, page: Page):
    """Clicking a graph node populates the detail panel."""
    page.goto(server_and_data)
    page.wait_for_load_state("networkidle")

    page.locator(".network-item").first.click()
    page.wait_for_selector(".message-bubble", timeout=5000)

    page.locator(".tab[data-tab='graph']").click()
    page.wait_for_selector("#graph-svg circle", timeout=6000)

    # Click first node
    page.locator("#graph-svg .node circle").first.click()
    page.wait_for_timeout(300)

    take(page, "04_graph_node_detail")

    # Detail panel should have persona name
    assert page.locator(".graph-detail .detail-name").is_visible()


def test_04b_graph_edge_click(server_and_data, page: Page):
    """Clicking a graph edge populates the relationship detail panel."""
    page.goto(server_and_data)
    page.wait_for_load_state("networkidle")

    page.locator(".network-item").first.click()
    page.wait_for_selector(".message-bubble", timeout=5000)

    page.locator(".tab[data-tab='graph']").click()
    page.wait_for_selector("#graph-svg line.link", timeout=6000)

    page.locator("#graph-svg line.link").first.click()
    page.wait_for_timeout(300)

    expect(page.locator(".graph-detail")).to_contain_text("Relationship")
    assert page.locator("#graph-svg line.link.selected").count() >= 1


def test_05_qa_view(server_and_data, page: Page):
    """QA tab shows QA cards with badges and expandable answers."""
    page.goto(server_and_data)
    page.wait_for_load_state("networkidle")

    page.locator(".network-item").first.click()
    page.wait_for_selector(".message-bubble", timeout=5000)

    page.locator(".tab[data-tab='qa']").click()
    page.wait_for_selector(".qa-card", timeout=5000)

    take(page, "05_qa_view")

    # QA cards present
    assert page.locator(".qa-card").count() >= 4

    # Filter buttons
    assert page.locator(".filter-btn").count() >= 2
    assert page.locator("#qa-review-summary").is_visible()
    assert page.locator(".qa-preview").count() >= 4


def test_06_qa_expand(server_and_data, page: Page):
    """Clicking a QA card expands it to show the answer and evidence."""
    page.goto(server_and_data)
    page.wait_for_load_state("networkidle")

    page.locator(".network-item").first.click()
    page.wait_for_selector(".message-bubble", timeout=5000)

    page.locator(".tab[data-tab='qa']").click()
    page.wait_for_selector(".qa-card", timeout=5000)

    # Expand first card
    page.locator(".qa-card").first.locator(".qa-card-header").click()
    page.wait_for_timeout(300)

    take(page, "06_qa_expanded")

    # Answer visible
    assert page.locator(".qa-card.expanded .qa-card-body").is_visible()


def test_07_qa_filter(server_and_data, page: Page):
    """QA filter buttons filter the displayed cards."""
    page.goto(server_and_data)
    page.wait_for_load_state("networkidle")

    page.locator(".network-item").first.click()
    page.wait_for_selector(".message-bubble", timeout=5000)

    page.locator(".tab[data-tab='qa']").click()
    page.wait_for_selector(".qa-card", timeout=5000)

    total = page.locator(".qa-card").count()

    # Click Q1 filter
    page.locator(".filter-btn[data-filter='Q1']").click()
    page.wait_for_timeout(200)

    take(page, "07_qa_filtered_q1")

    filtered = page.locator(".qa-card").count()
    assert filtered < total, "Filter should reduce card count"
    assert filtered >= 1, "At least 1 Q1 card expected"
    expect(page.locator("#qa-review-summary")).to_contain_text("in view")


def test_08_evidence_markers_in_chat(server_and_data, page: Page):
    """Messages cited as QA evidence show a 'cited in QX' marker."""
    page.goto(server_and_data)
    page.wait_for_load_state("networkidle")

    page.locator(".network-item").first.click()
    page.wait_for_selector(".message-bubble", timeout=5000)

    take(page, "08_evidence_markers")

    # At least one message should have an evidence-marker badge
    assert page.locator(".evidence-marker").count() >= 1


def test_09_evidence_jump_to_chat(server_and_data, page: Page):
    """Clicking 'view in chat' on a QA evidence item switches to Chat and focuses the message."""
    page.goto(server_and_data)
    page.wait_for_load_state("networkidle")

    page.locator(".network-item").first.click()
    page.wait_for_selector(".message-bubble", timeout=5000)

    # Go to QA tab and expand first card
    page.locator(".tab[data-tab='qa']").click()
    page.wait_for_selector(".qa-card", timeout=5000)
    page.locator(".qa-card").first.locator(".qa-card-header").click()
    page.wait_for_timeout(300)

    # Click the first "view in chat" jump button
    jump_btn = page.locator(".evidence-jump").first
    assert jump_btn.is_visible(), "Evidence jump button should be visible on expanded card"
    jump_btn.click()
    page.wait_for_timeout(600)

    take(page, "09_evidence_jump")

    # Should now be on Chat tab
    assert page.locator(".tab[data-tab='chat'].active").count() >= 1
    # Chat container should be visible and scrolled to the message
    assert page.locator("#chat-container").is_visible()
    assert page.locator(".msg-group.highlighted").count() >= 1


# ── Run directly ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
