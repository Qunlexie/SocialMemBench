# SocialMemBench: Data Generation Pipeline

## What This Is

SocialMemBench is a novel synthetic benchmark for evaluating AI memory in social group conversations — friends, family, recreational clubs, interest communities, acquaintance networks. No existing benchmark covers this space. EverMemBench (Feb 2026, the closest work) is locked to workplace/enterprise settings.

**Novelty confirmed**: No benchmark combines synthetic social group conversations + speaker attribution + memory evaluation across friend/family/recreational/interest domains.

---

## Architecture Pivot: API → Skill Files

### Original approach (v1, abandoned)

The first implementation used the Anthropic Python SDK directly: a `ClaudeClient` wrapper made programmatic API calls from Python generators (`EgoNetworkGenerator`, `ConversationPipeline`, `QAGenerator`). This required an `ANTHROPIC_API_KEY` and made the pipeline feel like backend software rather than a research tool.

**Why we changed**: Running generation through the API is the wrong abstraction. Claude Code IS the model — it can read schema files, follow structured instructions, write JSON directly to disk, and update the manifest, all without a separate API layer. Skills are also easier to inspect, version, and improve than Python prompt templates buried in generator classes.

### Current approach (v2, active)

Generation runs through **Claude Code skill files** in `.claude/commands/`. The user invokes a skill from a Claude Code session; Claude reads the instruction file, generates data, and writes it to `data/`. No API key. No `anthropic` SDK. The Python layer is a thin utility layer only (schemas as spec documents, manifest I/O, metrics).

**Pipeline** (one network at a time):
```
/smb-generate-network {group_type} {group_size}
/smb-verify {network_id} --stage 1
/smb-generate-conversations {network_id} 5
/smb-verify {network_id} --stage 2
/smb-generate-qa {network_id}
/smb-qc {network_id}
/smb-verify {network_id} --stage 3
/smb-status
```

See `CLAUDE.md` for the full skill reference.

---

## Dataset Design (mirrors EverMemBench, adapted for social settings)

### EverMemBench reference format

EverMemBench (the benchmark we mirror) uses three HuggingFace splits:

**profiles** (170 rows):
```json
{
  "Name": "Weihua Zhang", "ID": "297ec1d7", "Age": "48",
  "Communication_Profile": {"Formality": "Semi-formal", "Emoji_Usage": "Rare", ...},
  "Big_Five_Profile": {"Openness": "High", "Conscientiousness": "High", ...}
}
```

**dialogues** (1.26k rows — grouped by date, then sub-group):
```json
{
  "topic_id": "01", "date": "2025-01-09",
  "dialogues": {
    "Group 1": [{"speaker": "Name", "time": "09:32:15", "dialogue": "...", "message_index": 1}]
  }
}
```

**qars** (2.4k rows):
```json
{
  "topic_id": "01", "id": "F_SH_Top01_001",
  "Q": "...", "A": "65%",
  "R": [{"date": "2025-10-20", "group": "Group 3", "message_index": "4"}]
}
```

### Our social-adapted format

**profiles** — replace Dept/Title/Rank/Tenure with social relationship fields:
```json
{
  "Name": "Sarah Chen", "ID": "a3f8c2d1", "Age": "27",
  "Group_Name": "Ridgeline Hikers", "Group_Type": "recreational",
  "Relationship_Type": "childhood_friend", "Closeness": "High",
  "Preferences": {
    "Activities": [{"value": "prefers flat trails", "confidence": "Medium", "implicit": true}]
  },
  "Preference_History": [
    {"domain": "activities", "old_value": "neutral on hiking", "new_value": "enthusiastic", "changed_at_session": 3, "trigger": "Mike invited her"}
  ],
  "Communication_Profile": {"Formality": "Casual", "Emoji_Usage": "Frequent", "Typo_Rate": "Moderate", ...},
  "Speaking_Quirks": ["uses 'tbh' and 'lol' frequently", "never uses full punctuation"]
}
```

**dialogues** — same structure, with hidden `_planted` metadata (stripped before release):
```json
{
  "group_id": "grp_001", "group_type": "recreational", "session_index": 3,
  "date": "Session 3, Saturday afternoon",
  "dialogues": {
    "Ridgeline Hikers": [
      {
        "speaker": "Mike", "time": "Session 3, 2:47pm",
        "dialogue": "depends on the trail tbh the last one nearly killed me",
        "message_index": 2,
        "_planted": {"challenge_type": "implicit_preference", "subject_id": "mike_001", "fact": {"attribute": "trail_difficulty", "value": "dislikes_steep"}}
      }
    ]
  }
}
```

**qars** — same structure + `query_type`:
```json
{
  "group_id": "grp_001", "id": "Q5_Top01_003",
  "query_type": "Q5", "query_type_label": "theory_of_mind_reference",
  "difficulty": "hard",
  "Q": "What is Mike's preference regarding trail steepness? Who revealed this?",
  "A": "Mike dislikes steep trails. Revealed by Sarah in Session 3.",
  "R": [{"session_index": 3, "group": "Ridgeline Hikers", "message_index": "2"}],
  "contamination_foil": null
}
```

---

## 8 Query Types (Q1–Q8)

| Type | Label | Challenge Source | Key Constraint |
|------|-------|-----------------|----------------|
| Q1 | single_contact_recall | `implicit_preference` | Single persona; difficulty = implicitness level |
| Q2 | group_decision_recall | `consensus_trap` | Must cover group decision AND dissenter's true preference |
| Q3 | multi_contact_aggregation | All `implicit_preference` on same domain | Complete breakdown — one entry per member |
| Q4 | contamination_probe | `false_attribution_seed` | Question must make both candidates plausible |
| Q5 | theory_of_mind_reference | `theory_of_mind` | Two-part: preference + who revealed it (speaker ≠ subject) |
| Q6 | norm_vs_individual | `consensus_trap` with `truly_universal=false` | "No — [name] actually prefers X" |
| Q7 | relational_edge_query | `relational_disclosure` | Cite in-chat evidence, not just background metadata |
| Q8 | temporal_preference_evolution | `temporal_shift` | Name old value, new value, and session when it changed |

---

## Project Structure

```
SocialMemBench/
├── CLAUDE.md                        # skill reference + workflow entry point
├── PLAN.md                          # this document
├── pyproject.toml                   # pydantic, datasets, numpy, rich (no anthropic)
├── .claude/
│   └── commands/                    # Claude Code skill files (the pipeline)
│       ├── smb-generate-network.md
│       ├── smb-generate-conversations.md
│       ├── smb-generate-qa.md
│       ├── smb-verify.md
│       ├── smb-qc.md
│       └── smb-status.md
├── socialmembench/
│   ├── schemas/
│   │   ├── persona.py               # EgoNetwork, Persona, RelationshipEdge, GroupNorm
│   │   ├── conversation.py          # ConversationCorpus, ConversationTurn, PlantedChallenge
│   │   └── qa.py                    # QAPair, EvidenceAnchor (Q1–Q8)
│   └── utils/
│       ├── manifest.py              # DatasetManifest — incremental tracking
│       ├── serialization.py         # JSON/JSONL I/O
│       └── metrics.py               # quality metrics (run with python -m)
└── data/
    ├── manifest.json                # auto-managed by skills — do not edit manually
    ├── raw/                         # Stage 1: one JSON per network
    ├── conversations/               # Stage 2: one JSON per network
    ├── qa/                          # Stage 3: one JSONL per network (append-only)
    └── verify/                      # verification + QC reports
```

---

## Incremental Scale Design

`data/manifest.json` is the heart of the pipeline. Every skill reads it before generating and updates it after. This ensures:

- **No redundancy**: each network has a sequential `seed` (provenance integer); each `challenge_id` is tracked in `consumed_challenge_ids` so no QA pair is generated twice
- **Prioritization**: `/smb-status` and `/smb-generate-network` both read `group_type_counts` and `query_type_counts` to target underrepresented categories
- **Resumability**: if a run fails mid-way, the manifest reflects what was already completed; rerunning picks up from where it left off

```json
{
  "version": "1.0",
  "next_seed": 3,
  "networks": {
    "grp_a1b2c3d4": {
      "group_type": "recreational", "group_size": 3, "seed": 1,
      "status": "verified", "n_sessions": 5, "n_qa": 18,
      "consumed_challenge_ids": ["ch_001abc", "ch_002def"]
    }
  },
  "qa_pairs_total": 18,
  "query_type_counts": {"Q1": 4, "Q2": 3, "Q3": 2, "Q4": 2, "Q5": 2, "Q6": 2, "Q7": 1, "Q8": 2},
  "group_type_counts": {"close_friends": 0, "family": 0, "recreational": 1, "interest_community": 0, "acquaintance_network": 0}
}
```

---

## Generation Targets

| Milestone | QA pairs | Networks | Notes |
|-----------|----------|----------|-------|
| Initial (manual review) | 50 | 2–3 | Verify quality before scaling |
| First scale | 1,000 | ~20 | 4 per group type, sizes 3 and 5 |
| Full dataset | 2,000+ | 40+ | 8 per group type, sizes 2/3/5/10 |

**Success criteria for the 50-pair milestone**:
- All 8 query types represented
- Q5 questions always ask both "what preference?" AND "who revealed it?"
- Q6 answers always name the dissenter explicitly
- Conversations feel like real group chats (not scripted dialogues)
- `/smb-verify` passes all stage 1–3 checks for every network
- `/smb-qc` Phase 1 blind-critic pass rate ≥ 70%

---

## Verification

After generating each network, run the full check sequence:
```
/smb-verify {network_id}        # structural checks (Stage 1 + 2 + 3)
/smb-qc {network_id}            # blind critic + evidence grounding on QA
/smb-status                     # manifest summary + progress
python -m socialmembench.utils.metrics --data_dir data/
```

Spot-check manually:
- **Q5**: does the answer name both the preference value AND the speaker who revealed it?
- **Q6**: does the answer name the dissenter, not just confirm the norm?
- **Q4**: is the `contamination_foil` a genuinely plausible wrong answer?
- **Conversations**: are planted challenges truly implicit (not "I prefer X" stated directly)?
