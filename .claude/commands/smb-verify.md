# Verify Data Quality

Run structured verification checks across one or more stages for a given network. Outputs a report to `data/verify/{network_id}.json`.

## Arguments
`$ARGUMENTS` — format: `{network_id}` or `{network_id} --stage 1` or `{network_id} --stage 2` or `{network_id} --stage 3`
- network_id: required
- --stage: which stages to check (default: all three)

## Steps

### 1. Load files
Based on which stages are requested, load:
- Stage 1: `data/raw/{network_id}.json`
- Stage 2: `data/conversations/{network_id}.json`
- Stage 3: `data/qa/{network_id}.jsonl` (read all lines)

---

## Stage 1 Checks — Network Quality

Read `data/raw/{network_id}.json` and run these checks:

| Check | Pass condition |
|-------|---------------|
| Required fields present | All of: network_id, group_name, group_type, group_size, seed, personas, edges, group_norms |
| Correct persona count | len(personas) == group_size |
| Closeness variety | Not all edges have closeness == "High" |
| Tense/mixed edge exists | At least 1 edge with sentiment in ["mixed", "tense"] |
| Contested norm exists | At least 1 group_norm with truly_universal == false AND len(dissenters) > 0 |
| Preference history coverage | Every persona has len(preference_history) >= 1 |
| Communication distinctness | No two personas share identical (formality, emoji_use, humor) triple; additionally, every pair of personas must differ on ≥2 of the 3 dimensions (verbosity, emoji_use, formality) — two personas that are both Casual + Moderate verbosity + Never-emoji are indistinct even if their humor types differ |
| Edge coverage | For group_size=3: ≥3 edges; for group_size=5: ≥6 edges |
| No null display_names | All personas have non-empty display_name |
| Persona IDs unique | All persona_id values are distinct |

---

## Stage 2 Checks — Conversation Quality

Read `data/conversations/{network_id}.json` and run:

| Check | Pass condition |
|-------|---------------|
| Sessions present | len(sessions) >= 1 |
| Turn count per session | Each session has 10–25 turns. Flag sessions with <10 as a failure; flag sessions with >25 as a warning. |
| Message format | Sample 5 random turns — each matches `[Session N, H:MMpm] Name: message` pattern |
| No out-of-character narration | No turn.message starts with "As [Name]", "*[Name]", or similar 3rd-person narration |
| Planted challenges exist | len(planted_challenge_index) >= 1 |
| Planted challenge field completeness | Every entry in planted_challenge_index must have all required fields non-null: `challenge_id`, `challenge_type`, `subject_persona_id`, `speaker_persona_id`, `fact_attribute`, `fact_value`, `evidence_span`, `implicitness_level`, `session_index`, `turn_index` |
| Challenge type variety | planted_challenge_index contains at least 3 distinct challenge_type values |
| Speaker coverage | Over all sessions, every persona appears as a speaker at least once |
| temporal_shift present | At least 1 challenge with challenge_type == "temporal_shift" |
| Evidence spans non-empty | All planted challenges have non-empty evidence_span |
| Evidence span verbatim | For a sample of 3 planted challenges: verify evidence_span is a verbatim substring of the actual turn message. Fail if any sampled span is not found in the corresponding turn. |
| Timestamp label consistency | For a sample of 5 turns across sessions: parse timestamp_label (e.g., "Mar 3, 7:12pm") and verify the hour and minute match the timestamp field (e.g., "2025-03-03T19:12:00"). Flag any mismatch as a failure. Also verify the date in timestamp_label matches the session date. |
| Day-of-week accuracy | For each session's date_label (e.g., "Session 1, Monday March 3, 2025 7:12pm"): compute the actual day of week from the session.date field and verify it matches the spelled-out day in date_label. Flag any mismatch (e.g., date_label says "Monday" but the date is a Wednesday). For day-name references inside messages (e.g., "see you Saturday", "last Tuesday"): speakers may reference past or future days — this is realistic. Verify only that the reference is calendar-consistent with the session date (e.g., if the session is Monday March 3, "this Saturday" should resolve to March 8; "last Friday" should resolve to Feb 28). Flag references where the named day is impossible given the session date (e.g., "see you yesterday, Sunday" when the session is Tuesday). |
| Session date continuity | Session dates must increase monotonically. For each consecutive session pair, verify session.date is present, valid ISO 8601, and strictly later than the previous session date. Flag missing dates or backward jumps as failures. |
| Message length ceiling | No single turn message exceeds 600 characters (hard fail). Flag any message over 400 characters as a warning. |
| Topic variation matches group type | `family`/`close_friends`: no near-duplicate primary topics across sessions; recurring umbrella threads are allowed but each session must have a distinct immediate concern. `interest_community`/`recreational`: primary domain should remain visible while at least 1 session includes a natural side-thread. `acquaintance_network`: moderate cross-session variance |
| Verbosity realized in transcript | `Verbose` personas have clearly longer messages in at least 2 sessions; `Terse` personas stay mostly short; `Concise`/`Moderate` personas sit between them, with occasional longer turns allowed when context justifies it |
| No em dashes in messages | Zero em dashes (`—`) in all `message` fields |

---

## Stage 3 Checks — QA Quality

Read `data/qa/{network_id}.jsonl` and run:

| Check | Pass condition |
|-------|---------------|
| QA pairs exist | File exists and has ≥1 line |
| No empty questions | All qa.question is non-empty |
| No empty answers | All qa.answer is non-empty |
| Answer length | All answers have ≥5 words |
| Evidence anchors | All QA pairs have ≥1 evidence_anchor |
| Evidence verbatim | For a sample of 5 pairs: message_excerpt from anchor is findable in the raw conversation text |
| Query type coverage | At least 4 distinct query_type values represented |
| Q5 two-part | All Q5 questions ask both what the subject's preference/attitude/behavior is and who knew, revealed, or figured it out |
| Q4 has foil | All Q4 pairs have non-null contamination_foil |
| Q4 foil quality | All Q4 contamination_foil values are ≥2 sentences AND reference a specific vocabulary or framing similarity between target and foil (not just "plausible wrong answer") |
| Q5 grounded ToM | All Q5 pairs' "who knew" evidence anchor points to an observable chat behavior (assumption, reaction, knowing reference) — not a description of a private conversation |
| Q8 has anchors | All Q8 pairs have temporal_anchors with ≥2 entries |
| Difficulty distribution | For each network: warn if >50% of pairs are labeled "easy"; warn if zero pairs are labeled "hard" |
| Inference depth present | If QC has been run: all pairs have `metadata.inference_required` set; warn if >20% are inference_required=0 |

---

### 2. Update manifest

Update `data/manifest.json` — always, regardless of pass/fail:
- Set `networks.{network_id}.verify` to:
  ```json
  {
    "overall_pass": true,
    "stage1_pass": true,
    "stage2_pass": true,
    "stage3_pass": true,
    "failure_count": 0,
    "verified_at": "{ISO 8601 timestamp}"
  }
  ```
  Set only the stage fields for stages that were actually checked; leave others null.
- If ALL checked stages pass: set `networks.{network_id}.status` to `"verified"` (or `"stage{N}_verified"` for single-stage runs)

### 3. Print summary
```
Verification: {network_id}
Stage 1: PASS ({n}/{total} checks) / FAIL ({n} failures)
Stage 2: PASS ({n}/{total} checks) / FAIL ({n} failures)
Stage 3: PASS ({n}/{total} checks) / FAIL ({n} failures)

Failures:
  [list each failure with fix suggestion]
```
