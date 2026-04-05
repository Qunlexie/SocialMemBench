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
- Q5: question doesn't contain both a preference-seeking component AND a "who" component → flag as "q5_single_part"
- Q8: temporal_anchors has < 2 entries → flag as "q8_insufficient_anchors"
- Q8: temporal_anchors all in consecutive sessions (e.g., session 3 and 4 only) → flag as "q8_consecutive_only"

### 5. Update QA pairs in the file

Rewrite `data/qa/{network_id}.jsonl` with updated fields:
- `qc_phase1_score`: blind critic similarity score (0.0–1.0)
- `qc_phase2_grounded`: true/false (null if phase 1 score < 0.5)
- `qc_phase3_flagged`: true/false
- `qc_phase3_flag_reason`: the flag reason string, or null

### 6. Output summary report to `data/qa/{network_id}_qc.json`
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
  ]
}
```

### 7. Print summary
```
QC Report: {network_id}
Total pairs: {n}
Phase 1 (blind critic): mean={score:.2f}, pass rate (≥0.70)={pct}%
Phase 2 (grounded): {pct}%
Phase 3 (structural flags): {n_flagged} flagged

Low-scoring pairs (score < 0.70):
  {list up to 5 with question + scores}

Flagged pairs:
  {list flags}

Full report: data/qa/{network_id}_qc.json
```
