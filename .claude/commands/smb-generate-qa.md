# Generate QA Pairs (Stage 3)

Generate question-answer pairs from a conversation corpus and append them to `data/qa/{network_id}.jsonl`.

## Arguments
`$ARGUMENTS` — format: `{network_id}` or `{network_id} Q1 Q5 Q8`
- network_id: required
- Optional: space-separated query type filter (e.g. `Q1 Q5`). If omitted, generate all applicable types.

## Steps

### 1. Load data
- Read `data/raw/{network_id}.json` — personas, edges, group_norms
- Read `data/conversations/{network_id}.json` — sessions, turns, planted_challenge_index
- Read `data/manifest.json` — get `networks.{network_id}.consumed_challenge_ids`

Skip any planted challenge whose `challenge_id` is already in `consumed_challenge_ids`.

### 2. Build the conversation index

For quick lookup, build a map: `turn_id → {session_index, speaker_display_name, message}`.

Also render the full corpus as plain text for reading:
```
--- Session 1, {date_label} ---
[Session 1, 2:47pm] Mike: message text
...
--- Session 2, {date_label} ---
...
```

### 3. Generate QA pairs

For each unconsumed planted challenge, generate the applicable QA types based on challenge_type:

---

#### Q1 — Single-Contact Recall
**Applies to**: `implicit_preference`
**Question**: Ask what {subject_name}'s preference is regarding {fact_attribute}. Do NOT reference the evidence span in the question.
**Answer**: State the preference clearly and directly.
**Difficulty**: implicitness_level 1 → easy, 2 → medium, 3 → hard
**Evidence anchor**: The turn containing the evidence_span.

---

#### Q2 — Group Decision Recall
**Applies to**: `consensus_trap`
**Question**: Two-part: (1) what did the group decide about {fact_attribute}? (2) did anyone prefer something different?
**Answer**: Cover both the group decision AND {subject_name}'s true preference.
**Difficulty**: how clearly the dissenter expressed their preference (implicitness_level).
**Evidence anchor**: The turn where the dissenter's reaction is visible.

---

#### Q3 — Multi-Contact Aggregation
**Applies to**: `implicit_preference` (only generate Q3 when ≥2 personas have challenges on the same fact_attribute)
**Question**: "Based on the conversations, what are each group member's preferences regarding {fact_attribute}?"
**Answer**: One entry per persona. For personas with no signal: "not mentioned" or "unclear".
**Difficulty**: hard if ≥2 personas have only partial signals; medium if 1 has no signal; easy if all clear.
**Evidence anchors**: All relevant turns (one per persona who expressed a preference).
**QC flag**: Skip if evidence comes from only 1 persona.

---

#### Q4 — Contamination Probe
**Applies to**: `false_attribution_seed`
**Setup**: speaker_persona_id is the TRUE source. subject_persona_id is the FOIL (plausible-but-wrong attribution).
**Question**: Ask who expressed/said [paraphrase of the statement] — phrase it so BOTH personas are plausible candidates. Do NOT name both in the question.
**Answer**: State clearly that {speaker_name} said it, with a brief evidence citation.
**contamination_foil**: Explain why {foil_name} is the plausible wrong answer (similar style, similar topic, etc.).
**Difficulty**: hard if communication profiles are similar; easy if clearly distinct.
**Evidence anchor**: The turn where the true speaker made the statement.
**QC flag**: Skip if the foil and target appear in the same turn.

---

#### Q5 — Theory of Mind Reference
**Applies to**: `theory_of_mind`
**Setup**: speaker_persona_id ≠ subject_persona_id. Speaker reveals subject's preference.
**Question (MUST be two-part)**: 
  1. "What is {subject_name}'s preference regarding {fact_attribute}?"
  2. "Who revealed this information?"
**Answer**: "{subject_name} prefers {fact_value}. This was revealed by {speaker_name} in Session {N} when they said [brief paraphrase]."
**Difficulty**: implicitness_level.
**Evidence anchor**: The turn where speaker makes the ToM reference.

---

#### Q6 — Social Norm vs Individual
**Applies to**: `consensus_trap` where the network has a group_norm with `truly_universal: false` and the subject_persona_id is in the dissenters list
**Question**: "The group described [paraphrase of norm]. Does this apply to everyone? If not, who has a different preference and what is it?"
**Answer**: "No — {dissenter_name} actually prefers {true_preference}. This was revealed when [brief evidence]."
**Do NOT** phrase the question as "Is X truly universal?" — too on the nose.
**Difficulty**: implicitness_level of the dissenter's reveal.
**Evidence anchor**: The turn showing the dissenter's implicit preference.

---

#### Q7 — Relational Edge Query
**Applies to**: `relational_disclosure`
**Question**: Ask about the relationship or shared history between speaker_persona and subject_persona, focusing on the fact_attribute.
**Answer**: Describe what was revealed IN THE CONVERSATION (not just metadata). Cite specific evidence.
**Difficulty**: hard if the revelation was only in background metadata (no conversation evidence); medium if in-chat.
**Evidence anchor**: The turn containing the relational disclosure.

---

#### Q8 — Temporal Preference Evolution
**Applies to**: `temporal_shift`
**Question**: "How did {subject_name}'s preference regarding {fact_attribute} change over the course of the conversations?"
**Answer**: 
  1. Early preference: {old_value} (cite session)
  2. Evolved preference: {new_value} (cite session)
  3. Approximate trigger if visible
**temporal_anchors**: `[{"session_index": X, "value": "{old_value}"}, {"session_index": Y, "value": "{new_value}"}]`
**Difficulty**: hard if sessions are ≥3 apart; medium if 2 apart; easy if consecutive.
**Evidence anchors**: Two turns — one from before the shift, one from after.
**QC flag**: Skip if temporal anchors are in consecutive sessions only AND there are other Q8 pairs already.

---

### 4. Self-QC before writing

Apply these rules and skip any pair that fails:
- Answer < 5 words → skip
- Q3: evidence from only 1 persona → skip
- Q4: foil and target appear in same turn → skip
- Q4: missing contamination_foil → skip
- Q5: answer doesn't name both the preference AND the speaker → skip
- Q8: fewer than 2 temporal_anchors → skip
- Any: empty question or answer → skip

### 5. Output format

Each QA pair as one JSONL line:
```json
{
  "qa_id": "Q{N}_{8-char hex}",
  "network_id": "{network_id}",
  "group_id": "{network_id}",
  "query_type": "Q1",
  "query_type_label": "single_contact_recall",
  "difficulty": "easy|medium|hard",
  "question": "...",
  "answer": "...",
  "evidence_anchors": [
    {
      "session_index": 1,
      "turn_id": "...",
      "speaker_display_name": "...",
      "message_excerpt": "exact quote, max 200 chars",
      "relevance": "why this is evidence"
    }
  ],
  "contamination_foil": null,
  "temporal_anchors": null,
  "qc_phase1_score": null,
  "qc_phase2_grounded": null,
  "qc_phase3_flagged": null,
  "qc_phase3_flag_reason": null,
  "source_challenge_id": "ch_...",
  "skill_version": "v1.0",
  "generation_seed": 0,
  "metadata": {}
}
```

Query type labels:
- Q1 → "single_contact_recall"
- Q2 → "group_decision_recall"
- Q3 → "multi_contact_aggregation"
- Q4 → "contamination_probe"
- Q5 → "theory_of_mind_reference"
- Q6 → "norm_vs_individual"
- Q7 → "relational_edge_query"
- Q8 → "temporal_preference_evolution"

### 6. Write files
1. Append each valid QA pair as a new line to `data/qa/{network_id}.jsonl` (create if it doesn't exist)
2. Update `data/manifest.json`:
   - For each QA pair: increment `query_type_counts.{query_type}`
   - Add `source_challenge_id` to `networks.{network_id}.consumed_challenge_ids`
   - Increment `qa_pairs_total` by the number of pairs generated
   - Increment `networks.{network_id}.n_qa` by the number of pairs generated

### 7. Report
```
QA pairs generated: {n_total}
Breakdown: Q1:{n} Q2:{n} Q3:{n} Q4:{n} Q5:{n} Q6:{n} Q7:{n} Q8:{n}
Skipped (self-QC): {n_skipped}
Appended to: data/qa/{network_id}.jsonl
Next step: /smb-qc {network_id}
```
