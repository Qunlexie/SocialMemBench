# QC — Blind Critic for QA Pairs (Stage 3)

Perform a blind critic pass on generated QA pairs for a network. The critic reads the raw conversation WITHOUT access to planted challenge metadata, attempts to answer each question independently, and scores how well the ground truth answer matches what the conversation actually supports.

## Arguments
`$ARGUMENTS` — format: `{network_id}`

## Steps

### 1. Load files
- Read `data/conversations/{network_id}.json`
- Render the full corpus as plain text (all sessions, all turns, in order):
  ```
  --- Session 1, {date_label} ---
  [Session 1, 2:47pm] Mike: message
  ...
  ```
- Read `data/qa/{network_id}.jsonl` — load all QA pairs

### 2. Blind critic test (for each QA pair)

**Critical**: Do NOT look at the planted challenge metadata when answering. Treat yourself as a fresh evaluator who has only read the conversation.

For each QA pair:
1. Read only the `question` field
2. Read only the plain-text conversation (no metadata)
3. Attempt to answer the question based solely on what is said in the conversation
4. Compare your answer to the ground-truth `answer` field
5. Score similarity 0.0–1.0:
   - 1.0: your answer matches the ground truth exactly in meaning
   - 0.7–0.9: mostly correct, minor omission or slight phrasing difference
   - 0.4–0.6: partially correct but missing key info or partially wrong
   - 0.0–0.3: your answer contradicts or is unrelated to the ground truth

### 3. Evidence grounding check (for each QA pair with score ≥ 0.5)

For each evidence_anchor in the pair:
1. Extract `message_excerpt`
2. Search the plain-text corpus for that excerpt verbatim (or near-verbatim, allowing for minor whitespace differences)
3. Check: does the `answer` logically follow from ONLY those excerpts, without needing additional context?

Mark `grounded: true` if both conditions hold.

### 4. Structural flags (rule-based)

Apply per query_type:
- Any type: answer < 5 words → flag as "answer_too_short"
- Q3: evidence_anchors all from same speaker → flag as "q3_single_persona"
- Q4: contamination_foil is null → flag as "q4_missing_foil"
- Q5: question doesn't contain both a preference/attitude/behavior-seeking component AND a "who knew/revealed/figured it out" component → flag as "q5_single_part"
- Q8: temporal_anchors has < 2 entries → flag as "q8_insufficient_anchors"
- Q8: temporal_anchors all in consecutive sessions (e.g., session 3 and 4 only) → flag as "q8_consecutive_only"

### 5. Conversation quality check

Read `data/raw/{network_id}.json` to get persona `communication_profile` fields. Then read the plain-text corpus and score the following 5 dimensions. This is separate from QA quality — it assesses the conversation itself.

For each dimension, score 0–2:
- **2**: clearly passes — no issues found
- **1**: minor issues but acceptable
- **0**: fails — specific turns or sessions need fixing

| Dimension | What to assess |
|-----------|---------------|
| `topic_diversity` | Sessions cover topics appropriate to the group-type model. `interest_community`/`recreational`: primary domain present in most sessions, with 1–2 natural digressions. `family`/`close_friends`: recurring umbrella concerns are fine, but each session must have a distinct immediate primary thread. `acquaintance_network`: moderate variance. |
| `voice_consistency` | Score each of 5 sub-dimensions across all personas (see detail below). Overall score = lowest sub-dimension score. |
| `naturalness_of_transitions` | Topic shifts are triggered by a character (someone brings something up), not cold jumps or announced pivots. |
| `em_dash_free` | Zero em dashes (`—`) in unprotected `message` fields. Protected text = planted turns and any turn text referenced by QA evidence anchors. Binary: 2 = none found in unprotected fields, 0 = any found there. Report protected counts separately in notes. |
| `planted_turn_integrity` | Planted challenge turns are unchanged. For each QA pair's `evidence_anchors`, verify the `message_excerpt` matches the actual message text verbatim. |

**Voice consistency — 5 sub-dimensions** (read each persona's `communication_profile` from the raw network file first):

| Sub-dimension | Pass criteria |
|--------------|--------------|
| `emoji_use` | `Never`: 0 emoji in all messages. `Rare`: ≤1 emoji per session on average. `Moderate`: emoji present in some sessions, absent in others. `Frequent`: majority of messages contain at least one emoji. Flag personas whose emoji density clearly contradicts their profile. |
| `typo_rate` | `None`: no typos anywhere. `Low`: ≤1 typo per session. `Moderate`: several typos per session. `High`: most messages contain at least one typo. Flag personas who are `None` but have typos, or `High` but are error-free. |
| `verbosity` | Use this model: `Terse` = almost all messages 1–8 words, rarely up to 15, never a paragraph; flag if median > 12 words. `Concise` = typical 8–20 words, occasionally up to ~40 when context demands, no multi-paragraph; flag if >20% of messages are <3 words or >10% exceed 60 words. `Verbose` = varies by group type (see below); flag accordingly. |
| `formality` | `Formal`: full sentences, correct punctuation, no slang, no fragments. `Semi-formal`: mostly sentences, minimal slang, occasional abbreviations. `Casual`: fragments, lowercase, abbreviations, no trailing punctuation expected. Flag clear violations (a Formal persona sending "lol ok" or a Casual persona writing in formal paragraphs). |
| `speaking_quirks` | Each persona has 2–3 speaking quirks defined. At least 1 quirk from each persona's list must be detectable across their turns in the corpus. Flag any persona where no quirk is present. |

**Verbose verbosity — group-type thresholds:**

| Group type | Verbose persona expectation | Flag if |
|-----------|---------------------------|---------|
| `interest_community` | 1–2 longer bursts (80–150 words) across the corpus — explanatory takes, knowledge dumps, detailed arguments | No message exceeds 50 words |
| `recreational` | Regular messages in the 30–60 word range; occasional push past 60 words for announcements, stories, or logistics | No message exceeds 25 words |
| `close_friends` | Longer messages appear in emotional or storytelling moments; no fixed burst requirement | Consistently at Terse levels (median under 12 words) |
| `family` | Similar to close_friends; longer messages appear around news, logistics, or conflict | Consistently at Terse levels (median under 12 words) |
| `acquaintance_network` | Similar to recreational; trending longer than Concise peers but no burst required | No message exceeds 25 words |

For any sub-dimension failure, list the specific persona and turns that caused it.

For any dimension scoring 0, list the specific session index and turn IDs that caused the failure.

This is an iterative QC-improvement workflow, not a one-pass check:
- If any conversation-quality dimension scores 0, revise only the implicated turns and rerun `/smb-verify` then `/smb-qc`
- A network is accepted only when all five dimensions score at least 1 and `em_dash_free` = 2
- If no prior accepted QC report exists for the network, treat the first accepted run as the baseline for later regression checks
- On later iterations, compare against the last accepted QC report and investigate any QA pair whose `qc_phase1_score` drops

Add to the output report under `conversation_quality`:
```json
"conversation_quality": {
  "topic_diversity": {"score": 2, "notes": ""},
  "voice_consistency": {"score": 2, "notes": ""},
  "naturalness_of_transitions": {"score": 2, "notes": ""},
  "em_dash_free": {"score": 2, "notes": ""},
  "planted_turn_integrity": {"score": 2, "notes": ""},
  "overall_pass": true,
  "failing_turns": []
}
```

`overall_pass` is true only if all 5 dimensions score ≥ 1 and `em_dash_free` = 2.

### 6. Update QA pairs in the file (QA fields only)

Rewrite `data/qa/{network_id}.jsonl` with updated fields:
- `qc_phase1_score`: blind critic similarity score (0.0–1.0)
- `qc_phase2_grounded`: true/false (null if phase 1 score < 0.5)
- `qc_phase3_flagged`: true/false
- `qc_phase3_flag_reason`: the flag reason string, or null

### 7. Output summary report to `data/qa/{network_id}_qc.json`
```json
{
  "network_id": "...",
  "total_pairs": 0,
  "phase1_mean_score": 0.0,
  "phase1_pass_rate": 0.0,
  "phase2_grounded_rate": 0.0,
  "phase3_flagged_count": 0,
  "by_query_type": {
    "Q1": {"count": 0, "mean_score": 0.0, "flagged": 0},
    ...
  },
  "flagged_pairs": [
    {"qa_id": "...", "query_type": "...", "flag": "...", "question": "..."}
  ],
  "low_score_pairs": [
    {"qa_id": "...", "query_type": "...", "score": 0.0, "your_answer": "...", "ground_truth": "..."}
  ],
  "conversation_quality": {
    "topic_diversity": {"score": 2, "notes": ""},
    "voice_consistency": {"score": 2, "notes": ""},
    "naturalness_of_transitions": {"score": 2, "notes": ""},
    "em_dash_free": {"score": 2, "notes": ""},
    "planted_turn_integrity": {"score": 2, "notes": ""},
    "overall_pass": true,
    "failing_turns": []
  },
  "baseline_reference": "none|accepted run timestamp or prior report path"
}
```

### 8. Print summary
```
QC Report: {network_id}
Total pairs: {n}
Phase 1 (blind critic): mean={score:.2f}, pass rate (≥0.70)={pct}%
Phase 2 (grounded): {pct}%
Phase 3 (structural flags): {n_flagged} flagged
Conversation quality: overall_pass={true|false}

Low-scoring pairs (score < 0.70):
  {list up to 5 with question + scores}

Flagged pairs:
  {list flags}

Conversation quality failures:
  {list failing dimensions with turns}

Full report: data/qa/{network_id}_qc.json
```
