# Generate Conversations (Stage 2)

Generate a WhatsApp-style conversation corpus for an existing network and save it to `data/conversations/`.

## Arguments
`$ARGUMENTS` — format: `{network_id} {n_sessions} [start_date]`
- network_id: the `network_id` from `data/raw/`
- n_sessions: how many sessions to generate (default: 5)
- start_date: ISO 8601 date for Session 1 (optional, e.g., `2025-03-03`). If omitted, pick a plausible recent Monday.

## Steps

### 1. Load data
- Read `data/raw/{network_id}.json` — study every persona's `display_name`, `communication_profile`, `speaking_quirks`, `preferences`, and `preference_history`
- Read `data/manifest.json`

### 2. Plan all sessions first (before writing any)

**Derive session dates:**
- Session 1 date = `start_date` (or the chosen Monday if not provided)
- Session N date = `start_date + (N-1) * 7 days`
- Format each date as ISO 8601 (e.g., `"2025-03-03"`)
- Compute the actual day of week for each session date (e.g., March 3 2025 = Monday). Use this in `date_label`. Speakers may freely reference past or future days ("see you Saturday", "last Tuesday") — this is realistic. Just ensure the reference is calendar-consistent: if the session is Monday March 3, "this Saturday" = March 8, "last Friday" = Feb 28. Never write a day reference that is impossible given the session date (e.g., "see you yesterday Sunday" when the session is Tuesday).

For each session (1 through n_sessions), decide:
- **Topic**: pick a topic that fits the group type's topic consistency profile (see below)
- **Active speakers**: 2-4 of the personas (vary who is active across sessions)
- **Planted challenges**: 2-4 per session. Distribute types across sessions:
  - Sessions 1-2: `implicit_preference`, `false_attribution_seed`, `relational_graph` (≥1 per session)
  - Sessions 2-3: `theory_of_mind`, `consensus_trap`
  - Sessions 3-5: `temporal_shift` (MUST include at least one in sessions 3-5), `relational_disclosure`
  - Never stack all of one type in a single session

For each planted challenge, record:
```json
{
  "challenge_type": "implicit_preference|theory_of_mind|consensus_trap|false_attribution_seed|temporal_shift|relational_disclosure",
  "subject_persona_id": "p_...",
  "speaker_persona_id": "p_...",
  "fact_attribute": "e.g., trail_difficulty",
  "fact_value": "e.g., dislikes steep trails",
  "implicitness_level": 2,
  "notes": "brief instruction — how to embed this implicitly"
}
```

### 3. Generate each session

**Format — every message on its own line, nothing else:**
```
[Session {N}, {H:MMpm}] {DisplayName}: {message}
```
No markdown. No asterisks. No headers. No narration. Just the chat lines.

**Implicitness levels:**
- Level 1 (AVOID): "I hate steep trails" — too direct, only use if plot requires it
- Level 2 (DEFAULT): complaint, reaction, passing comment — "my knees still haven't forgiven that last climb"
- Level 3 (HARDEST): silence, deflection, or subject change — persona goes quiet when steep trail is suggested

**Topic consistency model — pick topics that match the group type's real behavior:**

| Group type | Topic pattern | How to apply |
|-----------|--------------|--------------|
| `interest_community` | Strong primary topic (the shared interest) anchors most sessions | Sessions 1, 2, 4 stay on-topic; sessions 3 and/or 5 drift to personal news, life updates, or unrelated chat before returning |
| `recreational` | Activity planning/debrief anchors most sessions | Backbone is the activity; 1-2 sessions drift naturally (injury, gear, social plans, something that came up on the day) |
| `close_friends` | No dominant topic — sessions cover clearly different subjects | Each session should have a distinct primary thread: work stress, dating, a funny thing that happened, money, a media debate, etc. |
| `family` | High variance — sessions can be about very different things | Rotate across domains: health, a sibling's news, logistics, a shared memory, home stuff. Don't repeat the same domain in consecutive sessions |
| `acquaintance_network` | Loosely anchored by shared context (neighborhood, alumni event, etc.) | Mix of shared-context sessions and personal-update sessions; less cohesive than friends |

**Topic transition rule:** shifts must be triggered by a character, not announced. Someone mentions their bad week → the group reacts → the thread changes. Never open a session with an unexplained new topic.

**Em dash rule:** no em dashes (`—`) in any `message` field. Use a comma, split into two sentences, or just end the message early. Em dashes are not how people type in chats.

**Challenge type instructions:**

`implicit_preference` — Subject's preference is revealed by THEIR OWN words, through behavior or complaint, not stated directly.

`theory_of_mind` — Speaker A mentions what they know about Speaker B's preference. Example: "didn't you say you hate the steep ones [Name]?" — only use if A and B have a relationship that would justify this knowledge.

`consensus_trap` — Group makes a decision (e.g., "let's go to Luigi's"), but one dissenter goes quiet, changes subject, or says "sure whatever" — their true preference is visible only implicitly. Mark the decision AND the dissenter's quiet reaction.

`false_attribution_seed` — Two different personas make similar-sounding statements about related topics in the same or adjacent sessions. The statements should be in each person's distinct voice but be easy to confuse. Don't put them in the same message or directly next to each other.

`temporal_shift` — A persona expresses a preference that CONTRADICTS their earlier preference (from a prior session). The shift should feel earned — something happened that would cause it. This is ground truth for Q8.

`relational_disclosure` — Reveal something about the history or nature of the relationship between two personas. It should emerge naturally through a reference, a joke, or a shared memory mention.

`relational_graph` — Reveal connection structure: how members originally met, sub-clique dynamics, closeness signals (inside jokes, callbacks), or relationship tension. Must correspond to an actual edge in `EgoNetwork.edges`. Use `fact_attribute` values: `connection_origin`, `sub_clique`, `closeness_signal`, or `tension_marker`. Sessions 1–2 must include at least one of these per session to surface the graph structure early.

**Persona voice rules (CRITICAL):**
- Every message must sound like that persona's `communication_profile`:
  - `emoji_use: Frequent` → use emojis liberally
  - `emoji_use: Never` → zero emojis
  - `typo_rate: High` → occasional typos, missing letters
  - `typo_rate: None` → perfect spelling
  - `verbosity: Terse` → almost all messages 1–8 words; occasionally up to 15 words but rare; never a paragraph
  - `verbosity: Concise` → typical messages 8–20 words; occasionally up to ~40 words when context demands; no multi-paragraph
  - `verbosity: Verbose` → typical messages 20–60 words. How often they post longer bursts depends on group type:
    - `interest_community`: Verbose personas should post 1–2 longer bursts (80–150 words) across the corpus. Long explanatory messages — a detailed take on the shared interest, a knowledge dump, a rant — are natural and expected here. If a Verbose persona in an interest_community never posts a burst over 50 words, that is a voice failure.
    - `recreational` / `close_friends` / `family` / `acquaintance_network`: Verbose personas trend longer than others but group norms lean conversational. They should regularly write messages in the 30–60 word range and occasionally push past 60 words in an emotionally resonant or detailed moment (logistics, a story, an announcement). A Verbose persona in these groups should not look Concise — but a multi-paragraph burst is optional, not required. Flag only if no messages exceed 25 words.
  - `formality: Casual` → no punctuation at end, abbreviations, slang
  - `humor: Playful` → jokes, teasing, banter
- Enforce `speaking_quirks` — if quirks say "uses 'tbh' often", use it
- Different personas must be distinguishable by message style alone
- Allow occasional verbosity bursts from `Concise` or `Moderate` speakers when context warrants it (storytelling, explanation, defensiveness, logistics dump), but keep that occasional so persona distinctions remain visible
- In knowledge-heavy or interest-based groups, it is good for some members to occasionally write longer explanatory messages instead of everything being clipped chat fragments

**Natural flow rules:**
- Short reactions between longer messages (emojis, "haha", "true", "😭")
- Occasional topic drift is fine
- 10–25 messages per session
- Messages react to what was just said — not a monologue sequence

**Self-critique before moving to next session:**
After writing each session, score these 5 dimensions in your thinking (don't output the scores):
1. Voice consistency: Could I identify each speaker from message style alone?
2. Planting quality: Are the challenges embedded implicitly, or did I write "I prefer X" anywhere?
3. Cross-ref accuracy: Do third-party references match the referenced persona's actual profile?
4. Natural flow: Does it feel like a real chat, not a scripted dialogue?
5. Norm clarity: Are group habits stated as "we always X" not "I always X"?

If any score is clearly poor, rewrite the session before continuing.

Before finalizing the full corpus, do one more mental pass against the QC rubric:
- `topic_diversity`: matches the group-type topic model across sessions
- `voice_consistency`: each persona still sounds like themselves
- `naturalness_of_transitions`: any digression begins because a character introduces it naturally
- `em_dash_free`: zero em dashes in all `message` fields
- `planted_turn_integrity`: planted challenge turns should not need cleanup after generation

**Rolling context:** After each session, write a 3-5 sentence summary (for your own use as context when writing the next session). This summary tracks: decisions made, preferences revealed, relationship dynamics observed.

### 4. Attach planted challenges to turns

After generating all sessions, go back and identify which turn best expresses each planted challenge:
- Match speaker + key words from `fact_value`
- Record `turn_index` (0-indexed position in session.turns), `evidence_span` (exact quote, max 200 chars)

### 5. Build the output JSON

```json
{
  "network_id": "{network_id}",
  "start_date": "{start_date}",
  "sessions": [
    {
      "session_id": "{network_id}_s{01}",
      "network_id": "{network_id}",
      "session_index": 1,
      "topic": "...",
      "date": "{start_date}",
      "date_label": "Session 1, {Day} {Month} {D}, {YYYY} {H:MMam/pm}",
      "turns": [
        {
          "turn_id": "{session_id}_t{000}",
          "session_id": "...",
          "speaker_persona_id": "p_...",
          "speaker_display_name": "...",
          "timestamp_label": "{Mon} {D}, {H:MMam/pm}",
          "timestamp": "{YYYY-MM-DDTHH:MM:00}",
          "message": "...",
          "message_index": 1,
          "planted_challenges": [
            {
              "challenge_id": "ch_{8-char hex}",
              "challenge_type": "...",
              "subject_persona_id": "...",
              "speaker_persona_id": "...",
              "fact_attribute": "...",
              "fact_value": "...",
              "evidence_span": "...",
              "implicitness_level": 2,
              "session_index": 1,
              "turn_index": 0
            }
          ],
          "reply_to_turn_id": null
        }
      ],
      "prior_session_summary": null,
      "critic_scores": null,
      "generation_attempts": 1
    }
  ],
  "total_turns": 0,
  "planted_challenge_index": []
}
```

Set `total_turns` to the actual count. `planted_challenge_index` should be a flat list of all `PlantedChallenge` objects from all turns.

### 6. Write files
1. Write to `data/conversations/{network_id}.json`
2. Update `data/manifest.json`:
   - Set `networks.{network_id}.status` to `"stage2_done"`
   - Set `networks.{network_id}.n_sessions` to the count

### 7. Report
```
Conversations generated: {network_id}
Sessions: {n} | Total turns: {total_turns}
Planted challenges: {n_total} across {n_types} challenge types
Challenge type breakdown: {type: count, ...}
Next step: /smb-verify {network_id} --stage 2
```
