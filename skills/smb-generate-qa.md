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

### 3. Pre-generation inference gate

Before writing any QA pair, apply this universal **inference depth rubric**. Assign a level, then check it matches the intended difficulty:

| Level | Label | What it requires |
|-------|-------|-----------------|
| 0 | **Reject** | Answerable by keyword or name search — find one word and you have the answer |
| 1 | **Easy** | Single-turn lookup — answer is stated in one place, no inference needed |
| 2 | **Medium** | 2-turn synthesis OR one inference step — requires connecting two pieces of evidence |
| 3 | **Hard** | Cross-session inference OR attribution ambiguity — requires tracking signals across ≥3 turns or distinguishing two plausible speakers by meaning, not surface marker |

**Surface pattern test (apply before writing):** Ask yourself: "Could this question be answered by searching the transcript for a single keyword or name?" If yes → either reframe the question so it requires inference, or skip the pair entirely.

Examples of reject-level questions that must be reframed or skipped:
- "What does the conversation reveal about Maya's attitude toward cilantro?" — "cilantro" keyword gives it away
- "Did Sam seem reluctant about the rooftop bar?" — "..." and "sure" are visible without inference
- "How did Jordan's role change?" — a one-sentence summary of an explicit reference

Reframed versions that pass:
- "What does Maya's behavior at group dinners suggest about her food preferences?" — requires synthesizing avoidance patterns
- "How did Sam signal their true feeling about the rooftop bar choice, and what made it easy to miss?" — requires reading implicit dissent
- "What in Sessions 2–3 signaled that Jordan was stepping back from their previous organizing role?" — requires tracking mechanism across sessions

**Difficulty label must match inference level:** easy → level 1, medium → level 2, hard → level 3. Any pair where the label doesn't match the rubric must be corrected before writing.

---

### 3.5 Question-phrasing rule: no session-index direct recall

Questions must read like something a real Class 1 (group-acting AI) or Class 2 (personal-observing AI) user would actually type. Real users never reference session indices. They use natural anchors: topics, events, dates, or relative phase.

Session references in the QUESTION TEXT are tightly constrained.

**Allowed in question text** (natural anchors):
- Topic anchors — "the conversation about the parking scheme", "when the group discussed dinner plans"
- Causal / event anchors — "before Marcus left", "after Sarah brought up the move", "when Bex announced her trip"
- Phase anchors — "earlier in the group's history", "later", "in the early conversations", "in their later interactions"
- Date anchors using `date_label` — "the September meetup", "the late-November exchange"

**Forbidden in question text** (artifact direct recall):
- `In Session N, ...` prefix — *forbidden*
- `in which session did X` / `where in Sessions N–M` — *forbidden* (asks the system to output a session index)
- `what in Session N signals` / `from Session N` / `Sessions N and later` — *forbidden* (uses the index as a temporal anchor)
- Any phrasing where the answer must include a session number — *forbidden*

The deletion rule for borderline cases: if removing a session reference would make the question ambiguous, replace with a natural anchor (use the conversation's actual `date_label` or a topic anchor from the planted challenge). If you cannot find a natural anchor, the question is testing the wrong thing — reframe or reject.

**What about evidence_anchors?** Internal evaluation metadata (`evidence_anchors`, `temporal_anchors`) MUST keep `session_index` — that's how the eval harness verifies groundedness. The rule is about USER-FACING question text, not internal metadata.

**Self-QC regex check (apply before writing):**
- Question text must not match `[Ss]ession\s*\d+` — if it does, reframe or reject
- Question text must not match `\bin which session\b` — reframe or reject

Examples:

Reject (artifact recall):
- "In Session 5, what does Marcus say about the move?"
- "What was Bex's dietary practice — and in which session did she make it most explicit?"
- "What in Session 6 signals Claire's approach changed?"

Reframed versions that pass:
- "What does Marcus reveal about his feelings about the move?" *(drop the prefix; the topic is the anchor)*
- "What was Bex's dietary practice, and what specifically makes it visible in the group's interactions?" *(drop the compound clause)*
- "What signals that Claire's approach to group exercise has changed, and what appears to have driven it?" *(replace session ref with natural temporal phrasing)*

---

### 4. Generate QA pairs (one per applicable challenge, after passing the inference gate)

**Answer format rules (apply per query type):**

| Q type | answer_format | options / correct_option |
|--------|--------------|--------------------------|
| Q1 | `long_form` | null |
| Q2 | `multiple_choice` | options = group member names as A/B/C/D (shuffled); correct_option = letter of dissenter |
| Q3 | `long_form` | null |
| Q4 | `multiple_choice` | options = group member names as A/B/C/D (shuffled); correct_option = letter of true speaker |
| Q5 | `long_form` | null |
| Q6 | `multiple_choice` | options = group member names as A/B/C/D (shuffled); correct_option = letter of dissenter |
| Q7 | `short_answer` | correct_option = relationship type as short phrase (e.g., "childhood friends") |
| Q8 | `long_form` | null |
| Q9 | `long_form` | null |

For MC questions (Q2/Q4/Q6): shuffle the persona names randomly across A/B/C/D. Always include all group members as options (max 4 options for groups of 4–5; if 5 members, pick the 4 most plausible). `answer` still contains the full explanation.

For short_answer (Q7): `correct_option` is the concise scoreable value. `answer` still contains full evidence-grounded explanation.

For each unconsumed planted challenge, generate the applicable QA types based on challenge_type:

---

#### Q1 — Single-Contact Recall
**Applies to**: `implicit_preference`
**Question**: Ask about {subject_name}'s behavior, pattern, or attitude — NOT the specific preference keyword. Do NOT name the fact_attribute or any keyword from the evidence_span in the question. Frame it around observable behavior ("what does X's behavior suggest about…", "how does X typically respond when…").
**Answer**: State the preference clearly and trace it through ≥2 turns. A single-turn citation is only acceptable for easy pairs.
**Difficulty**: implicitness_level 1 → easy, 2 → medium, 3 → hard. Apply inference rubric: if the fact_attribute word appears in the conversation and the question could be answered by searching for it, reframe or reject.
**Evidence anchor**: The turn(s) containing the evidence_span. Medium/hard pairs must cite ≥2 anchors.

---

#### Q2 — Group Decision Recall
**Applies to**: `consensus_trap`
**Question**: Two-part: (1) what did the group decide about {fact_attribute}? (2) did anyone seem less than fully on board, and how could you tell?

**For implicitness_level=3 (non-verbal dissent — silence, "...", "sure", one-word reply):** The question MUST ask about mechanism, not just identity. It must contain a mechanism-seeking phrase such as "what did [Person]'s response signal about", "what specifically in how they responded", "what did [Person]'s reaction reveal about". A question that only asks "did everyone agree?" or "who seemed reluctant?" fails this test — rewrite it before writing.

Weak (reject): "Did everyone seem fully on board with [decision]?"
Weak (reject): "Who seemed reluctant about [decision], and how could you tell?"
Strong (pass): "What did [Person]'s response to [decision] signal about their actual position, and what specifically in how they responded tells you that?"
Strong (pass): "The group settled on [decision]. What did [Person]'s reaction in that moment reveal about how they actually felt, and how would you have known?"

**Answer**: Cover both the group decision AND {subject_name}'s implicit dissent — explain the specific signal (silence, deflection, minimal agreement) and what it suggests.
**Difficulty**: how clearly the dissenter expressed their preference (implicitness_level). Label "hard" only if the dissenter signal appears in ≤1 turn AND the signal is non-verbal (silence, "...", "sure"). If the dissenter explicitly states a preference, cap at medium.
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
**Question**: Ask who expressed/said [paraphrase of the statement] — phrase it so BOTH personas are plausible candidates. Do NOT name both in the question. The paraphrase must be abstract enough that both speaker and foil could plausibly have said it.
**Answer**: State clearly that {speaker_name} said it, with a brief evidence citation explaining what distinguishes their phrasing.
**contamination_foil**: MUST explain (a) why {foil_name} is the plausible wrong answer — specifically what vocabulary, topic, or framing makes them a plausible author, AND (b) what the listener must notice to correctly attribute the statement to the true speaker. A foil explanation that only says "plausible because they discuss similar topics" is not sufficient.
**Difficulty gate**: Only write this pair if both the target and foil use similar surface framing or vocabulary on the topic. If one speaker is dramatically more talkative, more formal, or uses a clearly different register — the probe is too easy. Skip it.
**Difficulty**: hard if communication profiles are similar AND the distinction rests on meaning, not style; easy if clearly distinct voice or register.
**Evidence anchor**: The turn where the true speaker made the statement.
**QC flag**: Skip if the foil and target appear in the same turn.

---

#### Q5 — Theory of Mind Reference
**Applies to**: `theory_of_mind`
**Setup**: speaker_persona_id ≠ subject_persona_id. Speaker reveals subject's preference.
**Question (MUST be two-part)**: 
  1. "What is {subject_name}'s attitude/preference/feeling regarding {fact_attribute}?"
  2. "How does {speaker_name} know this — what in the conversation shows they had this knowledge?"
**Answer**: "{subject_name} prefers {fact_value}. {speaker_name} revealed this in Session {N} when they [observable action/reaction]. This implies prior knowledge because [specific reasoning — what the speaker's reaction tells us about what they already knew]."
**Grounding rule**: The "who knew" evidence anchor MUST point to an observable reaction in the chat (e.g., an assumption made without asking, finishing someone's sentence, a knowing reference) — not an assertion that they had a private conversation. If the only evidence is "Josh revealed that he and Priya had spoken privately," that's a claim, not an observable. It only counts if there is behavior in the chat that substantiates the knowledge.
**Difficulty**: implicitness_level.
**Evidence anchor**: The turn where speaker makes the ToM reference, specifically citing the observable behavior that implies prior knowledge.

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
**Answer**: Describe ONLY what is implied or revealed by the conversation itself — observable behaviors, how they treat each other in chat, what they say or don't say. Do NOT include biographical background from raw persona metadata (e.g., "known each other since age 11", "attended the same event") unless that fact appears verbatim in a conversation turn. The answer must be derivable from reading the conversation alone.
**Difficulty**: hard if the revelation was only in background metadata (no conversation evidence) — in which case, skip this pair; medium if in-chat.
**Evidence anchor**: The turn containing the relational disclosure.
**QC flag**: Skip if the only evidence for the relationship comes from persona metadata with no observable signal in any turn.

---

#### Q8 — Temporal Preference Evolution
**Applies to**: `temporal_shift`
**Question**: Ask about the mechanism or trigger of change, not just the fact of change. The question MUST contain either a trigger-seeking word ("what drove", "what appeared to cause", "what explains", "what signalled", "why") or a mechanism-seeking frame ("how did X's behaviour first signal", "what in the conversation shows"). A question that only asks "how did X change" or "how has X's approach changed" fails this test — rewrite it before writing.

Weak (reject): "How did {subject_name}'s preference regarding {fact_attribute} change?"
Weak (reject): "How has {subject_name}'s approach to {fact_attribute} changed over the sessions?"
Weak (reject): "In which session did {subject_name}'s behaviour around {fact_attribute} first change?" — violates Section 3.5 (asks for a session index in the answer)
Strong (pass): "What in the conversation signals that {subject_name}'s relationship to {fact_attribute} shifted, and what appeared to drive it?"
Strong (pass): "When did {subject_name}'s behaviour around {fact_attribute} first change, and what in the conversation explains why?" — natural temporal anchor
**Answer**: 
  1. Early state: what the preference/behavior was and where it's evidenced (cite session)
  2. Shift signal: the specific turn or behavior that marks the change
  3. Trigger: what in the conversation appears to have caused the shift (or note if unstated)
  4. Evolved state: what the preference/behavior became (cite session)
**temporal_anchors**: `[{"session_index": X, "value": "{old_value}"}, {"session_index": Y, "value": "{new_value}"}]`
**Difficulty**: hard if sessions are ≥3 apart AND the trigger is only inferrable; medium if 2 apart or trigger is visible; easy if consecutive. Never label a pair "hard" if the change is stated explicitly in the conversation.
**Evidence anchors**: At minimum — one from before the shift, one from after. For hard pairs, also anchor the triggering turn if identifiable.
**QC flag**: Skip if temporal anchors are in consecutive sessions only AND there are other Q8 pairs already.

---

#### Q9 — Departed-Member Recall
**Applies to**: networks where `metadata.departure_events > 0`. The subject_persona_id is the member who departs; the question tests whether the system retains facts about that member after they stop appearing.

**Question**: Ask about the departed member's preference, pattern, behaviour, or last known state, anchored with a natural causal reference to their departure ("before {member} left", "while {member} was still in the group", "in the period before {member}'s departure"). The question must test **stale-state retention** — what was true about the member during their participation, not what happened during the departure event itself.

**Forbidden Q9 question shapes** (these test the wrong thing):
- "What were the details of {member}'s departure (dates, destination, plans)?" — tests recent-event recall, not stale state. Reject.
- "How did the group mark {member}'s leaving?" — tests the departure session itself, not preserved facts. Reject.
- "How does the group talk about {member} now?" — tests post-departure state. Reject.
- "In which session did {member} announce they were leaving?" — also violates Section 3.5. Reject.

**Strong Q9 question shapes**:
- "Before {member} left for {destination}, what was their pattern around {fact_attribute}, and what specifically in the conversation showed this?"
- "While {member} was still in the group, what preference had they consistently expressed about {fact_attribute}?"
- "What was {member}'s last known position on {fact_attribute} before they departed, and how do you know?"

**Answer**: State the preference/pattern/state, citing pre-departure evidence. Include the implicit signal that revealed it. Do not include departure logistics in the answer.

**Evidence anchor — strict rule**: Every evidence anchor MUST be from a session strictly BEFORE the departure session. If the departure session is `D`, all `evidence_anchors[*].session_index < D`. If any anchor sits in or after `D`, the question can be answered from recent context — reject and reframe.

**Difficulty**:
- *Easy*: anchor in session immediately before departure (D−1)
- *Medium*: anchor ≥2 sessions before departure (≤D−2)
- *Hard*: anchors only in early sessions (S1–S2 of an 8+ session corpus before a late departure) — tests deep stale-state retention

**Evidence anchors**: At minimum 1 anchor; medium/hard pairs cite ≥2 anchors all in pre-departure sessions.

**QC flag**: Skip if any evidence anchor is in or after the departure session. Skip if the question asks about the departure event itself, post-departure state, or session indices.

---

### 5. Self-QC before writing

Apply these rules and skip any pair that fails:
- Answer < 5 words → skip
- Q3: evidence from only 1 persona → skip
- Q4: foil and target appear in same turn → skip
- Q4: missing contamination_foil → skip
- Q4: contamination_foil explanation < 2 sentences OR doesn't name a specific vocabulary/framing similarity → skip
- Q5: answer doesn't name both the preference AND the speaker → skip
- Q5: "who knew" evidence anchor describes a claimed private conversation rather than an observable chat behavior → skip
- Q8: fewer than 2 temporal_anchors → skip
- Q8: question does not contain a trigger-seeking word ("what drove", "what caused", "what explains", "what signalled", "why") or mechanism-seeking frame ("how did X's behaviour first signal", "what in the conversation shows") → rewrite before writing, do not skip
- Q9: any evidence_anchor is in or after the departure session → skip (tests recent recall, not stale state)
- Q9: question asks about the departure event itself, post-departure state, or a session index → skip
- Any: empty question or answer → skip
- **Question-phrasing rule (Section 3.5)**: Question text must NOT match `[Ss]ession\s*\d+` or contain `\bin which session\b` → reframe with a natural anchor (topic, event, date, or relative phase) before writing; if no natural anchor is available, skip
- **Inference gate**: Apply the surface pattern test — if the question can be answered by searching for one keyword or name in the transcript → skip or reframe
- **Difficulty mismatch**: If difficulty label doesn't match the inference rubric level → correct the label or skip

### 6. Output format

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
  "answer_format": "long_form|multiple_choice|short_answer",
  "options": null,
  "correct_option": null,
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
- Q9 → "departed_member_recall"

### 7. Write files
1. Append each valid QA pair as a new line to `data/qa/{network_id}.jsonl` (create if it doesn't exist)
2. Update `data/manifest.json`:
   - For each QA pair: increment `query_type_counts.{query_type}`
   - Add `source_challenge_id` to `networks.{network_id}.consumed_challenge_ids`
   - Increment `qa_pairs_total` by the number of pairs generated
   - Increment `networks.{network_id}.n_qa` by the number of pairs generated

### 8. Report
```
QA pairs generated: {n_total}
Breakdown: Q1:{n} Q2:{n} Q3:{n} Q4:{n} Q5:{n} Q6:{n} Q7:{n} Q8:{n} Q9:{n}
Skipped (self-QC): {n_skipped}
  - Inference gate rejects: {n}
  - Other self-QC skips: {n}
Difficulty distribution: easy:{n} medium:{n} hard:{n}
Appended to: data/qa/{network_id}.jsonl
Next step: /smb-qc {network_id}
```
