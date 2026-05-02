# Generate Ego Network (Stage 1)

Generate one social group ego network for SocialMemBench and save it to `data/raw/`.

## Arguments
`$ARGUMENTS` — format: `{group_type} {group_size} [--sessions N] [--turns-per-session N] [--departures N]`
- `group_type`: one of `close_friends`, `family`, `recreational`, `interest_community`, `acquaintance_network`. If omitted, auto-select most-needed from manifest.
- `group_size`: integer. If omitted, default to 5.
- `--sessions N`: number of sessions to plan (stored in `metadata.sessions_planned`). Default: 5.
- `--turns-per-session N`: target number of turns per session (stored in `metadata.turns_per_session`). The conversation generator uses this to calibrate message volume. Default: 15.
- `--departures N`: number of personas that will depart mid-corpus (default: 0).

All parameters are set by the CLI from `TIER_CONFIG` — do not hardcode defaults in the prompt.

## Steps

### 1. Read the manifest
Read `data/manifest.json`. If it doesn't exist, create it with this structure:
```json
{
  "version": "1.0",
  "next_seed": 1,
  "networks": {},
  "qa_pairs_total": 0,
  "query_type_counts": {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0, "Q5": 0, "Q6": 0, "Q7": 0, "Q8": 0},
  "group_type_counts": {"close_friends": 0, "family": 0, "recreational": 0, "interest_community": 0, "acquaintance_network": 0}
}
```
Note the current `next_seed` value. This becomes the `seed` for this network.

### 2. Choose group name
Pick a realistic group name for the type:
- close_friends → "The Usual Crew", "Old Squad", "Sunday Group", "The Regulars"
- family → "Family Chat", "The [Surname] Family", "Fam"
- recreational → "Ridgeline Hikers", "Weekend Warriors", "Trail Blazers", "Book Club", "Game Night Crew"
- interest_community → "Photo Collective", "Cooking Circle", "Vinyl Heads", "Indie Film Fans", "Board Game Nerds"
- acquaintance_network → "Maple Street Neighbours", "Class of 2015", "Office Social", "Parent Group"

### 3. Generate the network (two passes in your thinking)

**Pass A — Skeleton**

Generate personas, relationship edges, and group norms. Use this exact JSON structure (output as `data/raw/{network_id}.json`):

```json
{
  "network_id": "grp_{8-char hex}",
  "group_name": "...",
  "group_type": "{group_type}",
  "group_size": {group_size},
  "seed": {next_seed},
  "personas": [
    {
      "persona_id": "p_{8-char hex}",
      "display_name": "...",
      "age": 0,
      "gender": "...",
      "occupation": "...",
      "background": "...",
      "skills_list": [
        {"skill": "...", "proficiency": "strong|medium|low"},
        {"skill": "...", "proficiency": "strong|medium|low"}
      ],
      "big_five": {
        "openness": "High|Medium|Low",
        "conscientiousness": "High|Medium|Low",
        "extraversion": "High|Medium|Low",
        "agreeableness": "High|Medium|Low",
        "neuroticism": "High|Medium|Low"
      },
      "communication_profile": {
        "formality": "Casual|Semi-formal|Formal",
        "verbosity": "Terse|Concise|Verbose",
        "emoji_use": "Never|Rare|Moderate|Frequent",
        "humor": "Dry|Minimal|Playful|Expressive",
        "directness": "Indirect|Balanced|Direct|Blunt",
        "typo_rate": "None|Low|Moderate|High",
        "warmth": "Cool|Neutral|Friendly|Warm"
      },
      "preferences": {
        "food": [{"value": "...", "confidence": "High|Medium|Low", "implicit": true}],
        "activities": [],
        "social": [],
        "domain_specific": [{"value": "...", "confidence": "...", "implicit": true}]
      },
      "preference_history": [
        {
          "domain": "...",
          "attribute": "...",
          "old_value": "...",
          "new_value": "...",
          "changed_at_session": 3,
          "trigger": "..."
        }
      ],
      "speaking_quirks": ["...", "..."]
    }
  ],
  "edges": [
    {
      "persona_a_id": "...",
      "persona_b_id": "...",
      "relationship_type": "...",
      "closeness": "High|Medium|Low",
      "sentiment": "positive|neutral|mixed|tense",
      "history_summary": "...",
      "shared_events": ["...", "..."]
    }
  ],
  "group_norms": [
    {
      "norm_text": "...",
      "truly_universal": true,
      "dissenters": []
    }
  ],
  "metadata": {}
}
```

**Pass B — Enrich**

Now go back and fill in rich details for each persona:
- `occupation`: one-line job title or role — must be consistent with `background`
- `skills_list`: 2–4 items drawn from hobbies, interests, or talents relevant to this group type. Use proficiency levels honestly. These are personal skills, not credentials.
- `preferences`: 1-3 items per category; make them specific and implicit (revealed through behavior, not statements)
- `preference_history`: ≥1 event per persona — must include a session reference within the planned session range (e.g., `changed_at_session: 3` for a 5-session network, `changed_at_session: 5` for an 8-session network)
- `speaking_quirks`: 2-3 distinctive patterns per person that differ across personas
- `participation_rate`: for small networks (size ≤ 6): 1.0. For medium (7–14): 0.7–1.0. For large (15–30): 0.3–0.8. Vary across personas.

**If `--departures N > 0`:** select N personas to depart. For each:
- Set `status: "departed"`
- Set `departed_after_session` to a session index roughly 50–75% through the planned sessions. For a 5-session network, this would be session 3 or 4. For an 8-session network, session 4–6.
- Spread departure sessions across the corpus — don't stack all departures in the same session.
- Departing personas should be mid-closeness, not the group's most central member.

### 4. Social constraints checklist (MUST satisfy all)
Before writing the file, verify:
- [ ] Closeness is NOT all "High" — use at least one "Medium" and one "Low" across edges
- [ ] At least 1 edge has sentiment "mixed" or "tense"
- [ ] At least 1 group norm has `truly_universal: false` with a non-empty `dissenters` list (Q6 ground truth)
- [ ] Every persona has ≥1 `preference_history` event (Q8 ground truth)
- [ ] Communication profiles are measurably distinct — no two personas share the same formality + emoji_use + humor combination
- [ ] Edges cover all persona pairs (for group_size=3: 3 edges; for group_size=5: at least 6 edges; for group_size=9: at least 12 edges)
- [ ] Every persona has `occupation` set and `skills_list` with 2–4 items
- [ ] Skills are varied across personas — not all the same hobbies
- [ ] If departures > 0: departed personas have `status: "departed"` and a valid `departed_after_session`

### 5. Write files
1. Write the complete JSON to `data/raw/{network_id}.json`, including in `metadata`:
   ```json
   "metadata": {
     "sessions_planned": {n_sessions},
     "turns_per_session": {n_turns_per_session},
     "departures": {n_departures}
   }
   ```
2. Update `data/manifest.json`:
   - Set `networks.{network_id}` to:
     ```json
     {
       "network_id": "{network_id}",
       "group_type": "{group_type}",
       "group_size": {group_size},
       "tier": "{tier inferred from group_size: ≤6=small, 7-14=medium, ≥15=large}",
       "seed": {seed},
       "status": "stage1_done",
       "n_sessions": 0,
       "n_qa": 0,
       "consumed_challenge_ids": []
     }
     ```
   - Increment `next_seed` by 1
   - Increment `group_type_counts.{group_type}` by 1
   - Increment `size_tier_counts.{tier}` by 1

### 6. Report
Print a summary:
```
Network created: {group_name} ({network_id})
Tier: {tier} | Group type: {group_type} | Size: {group_size} | Seed: {seed}
Sessions planned: {n_sessions} | Departures: {n_departures}
Personas: {comma-separated display names}
  Departing: {comma-separated display names of departed personas, or "none"}
Norms: {n} total, {n_contested} contested
Next step: smb generate-conversations {network_id}
```
