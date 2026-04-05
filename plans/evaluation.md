# Evaluation Plan (Stage 4–5)

## Status: Planned — to be designed after first 50 conversations are generated and manually verified.

---

## Context

EverMemBench found that oracle models score only 26% on multi-hop attribution in workplace settings. We expect social settings to be harder — preferences are more implicit, norms have dissenters, and relationships carry personal history that changes over time.

The evaluation pipeline takes the generated QA pairs and measures how well AI models perform across all 8 query types.

---

## Stage 4: Model Evaluation

Feed each generated conversation corpus to a target model, ask the Q1–Q8 questions, and collect responses.

**Planned skill**: `/smb-evaluate {model} {network_id}`
- Renders the full conversation corpus as plain text (no planted challenge metadata)
- Asks each question from `data/qa/{network_id}.jsonl` to the model
- Records the model's answer alongside the ground truth
- Writes results to `data/results/{model}/{network_id}.jsonl`

**Questions to answer during design**:
- How much conversation context does the model receive? Full corpus or session-by-session?
- Does the model get the question cold (no conversation recap) or with a brief framing?
- Do we test with and without retrieval augmentation?
- Which models to evaluate first? (Claude, GPT-4, Gemini are natural starting points given EverMemBench used Gemini-2.5-Pro as its pipeline model)

---

## Stage 5: Scoring and Analysis

**Planned skills**:
- `/smb-score {model}` — per-type accuracy, difficulty breakdown, failure analysis
- `/smb-compare {model_a} {model_b}` — head-to-head across query types

**Metrics to compute**:
- Per query type accuracy (Q1–Q8 separately — this is the key contribution)
- Per difficulty level (easy / medium / hard)
- Per group type (close friends vs. acquaintance network — do social dynamics affect performance?)
- Attribution error rate (Q4, Q5 specifically — how often does the model blame the wrong person?)
- Norm confusion rate (Q6 — how often does the model state a contested norm as universal?)
- Temporal drift rate (Q8 — how often does the model report the old preference instead of the evolved one?)

**Scoring approach** (to be finalized):
- Option A: Exact match against ground truth answer (simple but brittle for free-form answers)
- Option B: LLM-as-judge — Claude reads the question, ground truth, and model answer, scores correctness 0–1
- Option C: Hybrid — structured fields (difficulty, query_type) exact match; answer text scored by LLM judge

EverMemBench used human evaluation + automated ROUGE-style metrics. We should decide whether to match their methodology for comparability or improve on it.

**Human evaluation**: For the 50-pair pilot, manually score a random sample. Use this to calibrate any automated scoring.

---

## Expected Findings (hypotheses to test)

- Q1 (direct recall) will be easiest — models handle explicit memory well
- Q5 (theory-of-mind) and Q6 (norm vs. individual) will be hardest — require distinguishing who said what about whom, and recognizing that a stated norm has exceptions
- Q4 (contamination) performance will correlate with how distinct the two personas' communication styles are
- Q8 (temporal evolution) will degrade as the number of sessions between the old and new preference increases
- Performance will be lower for acquaintance networks than close friends — weaker-tie preferences are signaled more ambiguously

---

## Milestones

| Milestone | Goal |
|-----------|------|
| 100 QA pairs generated | Design evaluation protocol, run pilot on 1 model |
| Pilot results reviewed | Calibrate scoring, finalize evaluation skill |
| 1,000 QA pairs | Full evaluation across 2–3 models |
| Analysis complete | Per-type accuracy table, failure mode characterization |
| Paper-ready | Full results, comparison to EverMemBench baseline |
