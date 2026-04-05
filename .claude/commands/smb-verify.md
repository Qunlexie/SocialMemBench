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
| Communication distinctness | No two personas share identical (formality, emoji_use, humor) triple |
| Edge coverage | For group_size=3: ≥3 edges; for group_size=5: ≥6 edges |
| No null display_names | All personas have non-empty display_name |
| Persona IDs unique | All persona_id values are distinct |

---

## Stage 2 Checks — Conversation Quality

Read `data/conversations/{network_id}.json` and run:

| Check | Pass condition |
|-------|---------------|
| Sessions present | len(sessions) >= 1 |
| Turn count per session | Each session has 10-30 turns |
| Message format | Sample 5 random turns — each matches `[Session N, H:MMpm] Name: message` pattern |
| No out-of-character narration | No turn.message starts with "As [Name]", "*[Name]", or similar 3rd-person narration |
| Planted challenges exist | len(planted_challenge_index) >= 1 |
| Challenge type variety | planted_challenge_index contains at least 3 distinct challenge_type values |
| Speaker coverage | Over all sessions, every persona appears as a speaker at least once |
| temporal_shift present | At least 1 challenge with challenge_type == "temporal_shift" |
| Evidence spans non-empty | All planted challenges have non-empty evidence_span |

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
| Q5 two-part | All Q5 questions contain both "preference" and "reveal" (or "who") keywords |
| Q4 has foil | All Q4 pairs have non-null contamination_foil |
| Q8 has anchors | All Q8 pairs have temporal_anchors with ≥2 entries |

---

### 2. Build report

```json
{
  "network_id": "{network_id}",
  "verified_at": "{timestamp}",
  "overall_pass": true,
  "stages": {
    "stage1": {
      "pass": true,
      "checks": {
        "required_fields_present": {"pass": true, "detail": ""},
        "correct_persona_count": {"pass": true, "detail": ""},
        ...
      }
    },
    "stage2": {...},
    "stage3": {...}
  },
  "failures": [
    {"stage": 1, "check": "contested_norm_exists", "detail": "No group_norm with truly_universal=false found"}
  ],
  "fix_suggestions": [
    "Re-run /smb-generate-network to create a new network with contested norms, or manually edit data/raw/{network_id}.json"
  ]
}
```

### 3. Write report
Write to `data/verify/{network_id}.json`.

If ALL checks pass across all requested stages, also update `data/manifest.json`:
- Set `networks.{network_id}.status` to `"verified"` (or `"stage{N}_verified"` for single-stage runs)

### 4. Print summary
```
Verification: {network_id}
Stage 1: PASS ({n}/{total} checks) / FAIL ({n} failures)
Stage 2: PASS ({n}/{total} checks) / FAIL ({n} failures)  
Stage 3: PASS ({n}/{total} checks) / FAIL ({n} failures)

Failures:
  [list failures with fix suggestions]

Full report: data/verify/{network_id}.json
```
