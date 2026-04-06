# SocialMemBench: Data Generation Plan

## Goal

Generate a synthetic benchmark of social group conversations with hidden ground-truth memory challenges. Data is generated through Claude Code skill files — no API key needed. The Python layer is thin utilities only (schemas, manifest I/O, metrics).

**Pipeline** (one network at a time):
```
/smb-generate-network {group_type} {group_size}   → data/raw/{id}.json
/smb-generate-conversations {network_id}           → data/conversations/{id}.json
/smb-generate-qa {network_id}                      → data/qa/{id}.jsonl
/smb-verify {network_id}                           → data/verify/{id}.json
/smb-qc {network_id}                               → data/qa/{id}_qc.json
/smb-status                                        → manifest summary
```

---

## Experimental Variables

Four independent variables drive the benchmark's analytical depth. Each produces a distinct paper result when plotted against Q1–Q9 accuracy.

### 1. Group Size

| Tier | Size range | Sessions | Participation model |
|------|-----------|----------|---------------------|
| Small | 3–6 | 5 | All members active every session (rate = 1.0) |
| Medium | 7–14 | 8 | Most active (rate 0.7–1.0); occasional absences |
| Large | 15–30 | 12 | Core active (rate 0.6–0.8); peripheral (rate 0.3–0.5) |

Larger groups need more sessions because Q8 requires sufficient per-member turns. **Q8 viability rule**: only generate Q8 for members with ≥ 8 expected turns (participation_rate × sessions × avg_turns_per_session). At large scale, Q3 (multi-contact aggregation over 20+ members) is deliberately hard — memory systems likely cannot do it at all. Generate Q3 at all tiers; report degradation as a finding.

**Group type × size tier**:

| Group type | Small | Medium | Large |
|-----------|-------|--------|-------|
| close_friends | ✓ | ✓ | — |
| family | ✓ | ✓ | ✓ (extended family) |
| recreational | ✓ | ✓ | ✓ (clubs, running groups) |
| interest_community | ✓ | ✓ | ✓ (book clubs, gaming) |
| acquaintance_network | ✓ | ✓ | ✓ (neighborhood, alumni) |

### 2. Timespan

Short-span networks (5 weeks to 3 months) are the baseline. Longitudinal networks span 3 years with realistic dormancy and enable failure modes no short-span tier can test.

**What longitudinal unlocks**:
- Multi-stage Q8 (preference changed in year 1, again in year 3 — old value is now stale)
- Memory decay (system over-weights recent sessions, loses early context)
- Dormancy reactivation (member goes quiet for 6+ months, rejoins — system must retain pre-dormancy preferences)
- Long-gap cross-reference ("like that time in 2023 when...") — extended query subtype **Q8L**

**Session spacing model** for longitudinal networks — not uniform, realistic burst/dormancy pattern:
```
Year 1  ████░░████░░░░░░░░░████░░░░░░░░  active bursts, dormant gaps
Year 2  ░░░░░░░░░░████░░░░░░░░░░████░░░  long dormancy then reactivation
Year 3  ░░░░░██░░░░░░░░████████████████  sparse early, dense recent
```
Session gaps range from 1 week to 3+ months. Encoded in `ConversationSession.gap_days` — no special type needed.

**Group type × longitudinal**: close_friends ✓, family ✓, recreational ✓, interest_community ✓, acquaintance_network — (tend to dissolve).

### 3. Noise Level

Real group chats are mostly unrelated to any benchmark challenge. The planted signal is the needle; the surrounding conversation is the haystack. Noise level is a controlled variable: the surrounding turns are random and unstructured, but each planted challenge still maps to a recoverable evidence span. A human reviewer looking directly at the planted turn can always verify the evidence — what varies is how much irrelevant content surrounds it.

| Level | Signal ratio | What it feels like |
|-------|-------------|-------------------|
| `low` | ~50% relevant turns | Focused chat, mostly on topic |
| `medium` | ~25% relevant turns | Realistic — topic drifts, tangents, off-topic messages |
| `high` | ~10% relevant turns | Chaos — buried signal, genuine unstructured noise |

Default: `medium`. Encoded as `ConversationCorpus.noise_level`.

### 4. Member Departure

Members can leave a network mid-corpus. Departure enables two failure modes:
1. **Stale recall**: system answers using pre-departure evidence without flagging the member is gone
2. **False attribution**: post-departure turns attributed to a departed member due to voice similarity (Q4 with a temporal component)

Departure also enables **Q9** — *departed member recall*: "X left after session N — what was their last stated preference on Y?"

| Tier | Departure frequency |
|------|---------------------|
| Small / short-span | None or 1 max |
| Medium | 1–2 per network |
| Large | Common — expect churn |
| Longitudinal | Highly realistic over 3 years |

Encoded as `Persona.status` and `Persona.departed_after_session`.

---

## Dataset Design

Three data splits mirroring EverMemBench, adapted for social settings:

**profiles** — one row per persona. Includes communication profile, Big Five personality, preferences (implicit and explicit), preference history, speaking quirks, participation rate, and departure status.

**dialogues** — WhatsApp-style group chat sessions. Format: `[Session N, H:MMpm] Name: message`. Each session has hidden `_planted` metadata (stripped before release) that drives QA generation. Sessions carry `active_participants`, `gap_days`, and are surrounded by realistic noise turns.

**qars** — Q1–Q9 question–answer–reference triples. Each QA pair has a `query_type`, difficulty rating (easy/medium/hard), ground-truth answer, and evidence anchors pointing to specific turns.

### QA answer formats

| Q type | answer_format | Scoreable unit |
|--------|--------------|----------------|
| Q1 | long_form | `answer` |
| Q2 | multiple_choice | `correct_option` (letter of dissenter) |
| Q3 | long_form | `answer` |
| Q4 | multiple_choice | `correct_option` (letter of true speaker) |
| Q5 | long_form | `answer` |
| Q6 | multiple_choice | `correct_option` (letter of dissenter) |
| Q7 | short_answer | `correct_option` (e.g., "childhood friends") |
| Q8 | long_form | `answer` + `temporal_anchors` |
| Q8L | long_form | `answer` + full `temporal_anchors` chain |
| Q9 | long_form | `answer` + `departed_after_session` |

---

## Query Types

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
| Q8L | longitudinal_evolution | multi-session `temporal_shift` | Trace full preference arc over years |
| Q9 | departed_member_recall | `departure` + `implicit_preference` | Scope evidence to pre-departure period |

---

## Incremental Scale Design

`data/manifest.json` tracks every network, seed, session count, QA count, and consumed challenge IDs. Skills read it before generating and update it after — no redundancy, no lost work on partial runs.

The manifest also tracks `group_type_counts`, `query_type_counts`, and `size_tier_counts` so `/smb-status` and `/smb-generate-network` can target underrepresented categories automatically.

---

## Small Scale First

**The current 10 small-tier networks (77 QA) need manual review before any further scaling.** Generating more data before confirming data quality compounds problems.

Small-scale validation sequence:
1. Manual review of existing 77 QA — confirm Q4/Q5/Q6 are genuinely non-trivial; planted signals are truly implicit
2. Run `/smb-qc` on all 10 networks — target ≥ 70% blind-critic pass rate
3. Generate 1 medium-tier network + 1 large-tier network — verify Q8 viability at those tiers
4. Run Condition A oracle on reviewed QA — establish ceiling, confirm hypothesis
5. Decision point: if data quality and oracle results validate → scale

Only proceed to Phase 2 (memory system evaluation) after this validation passes.

---

## Generation Targets

| Milestone | Networks | QA pairs | Notes |
|-----------|----------|----------|-------|
| Manual review (now) | 10 | ~77 | All small tier — review before scaling |
| Tier validation | 15 | ~200 | +5 medium, +5 large; verify Q8 at each tier |
| First scale | 25 | ~800 | Fill small + medium tiers |
| Full dataset | 40 | ~1,350 | Add large tier |
| Longitudinal | 46 | ~1,650 | +6 longitudinal networks; Q8L and Q9 validated |

**Success criteria for manual review**:
- All 8 core query types represented
- Q5 always asks both "what preference?" AND "who revealed it?"
- Q6 always names the dissenter explicitly
- Q4 `contamination_foil` is a genuinely plausible wrong answer
- Conversations feel like real group chats — planted challenges are implicit, not stated directly
- `/smb-verify` passes all stage 1–3 checks
- `/smb-qc` blind-critic pass rate ≥ 70%

---

## Verification

After generating each network:
```
/smb-verify {network_id}        # structural checks (all stages)
/smb-qc {network_id}            # blind critic + evidence grounding
/smb-status                     # manifest summary + progress
python -m socialmembench.utils.metrics --data_dir data/
```

Spot-check manually:
- **Q5**: does the answer name both the preference value AND the speaker who revealed it?
- **Q6**: does the answer name the dissenter, not just confirm the norm?
- **Q4**: is the `contamination_foil` a genuinely plausible wrong answer?
- **Conversations**: are planted challenges truly implicit (not "I prefer X" stated directly)?
