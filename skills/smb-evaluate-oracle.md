# Evaluate: Oracle Condition (Condition A)

Run the oracle evaluation on a network's QA pairs. In the oracle condition, the full conversation corpus is provided as context when answering each question. This is the performance ceiling — perfect memory, no summarization, no retrieval.

## Arguments
`$ARGUMENTS` — format: `{network_id}`

## Steps

### 1. Load files
- Read `data/conversations/{network_id}.json`
- Read `data/qa/{network_id}.jsonl` — load all QA pairs
- Confirm at least one QA pair exists; abort with an error if none

### 2. Render conversation as plain text

Format every session and turn in order:
```
--- Session 1, {date_label} ---
[Session 1, 2:47pm] Mike: message
[Session 1, 2:48pm] Sarah: message
...

--- Session 2, {date_label} ---
...
```

Keep this rendering in memory — it is the oracle context for all questions.

### 3. Answer each question under oracle conditions

**Critical: answer BEFORE scoring.** For each QA pair, read only the `question` field, then answer it using only the rendered conversation above. Do NOT read the `answer` field yet.

Record your answer as `model_answer`. Be specific: name the persona, state the preference, describe the relationship, etc. A vague answer scores lower.

Query-type-specific answering guidance:
- **Q1** (single preference): Name the persona and state what their preference is, as inferred from the conversation.
- **Q2** (group decision): State the decision and name any dissenters.
- **Q3** (multi-contact): Go through each group member and state their preference on the domain. If a member's preference is unknown, say so.
- **Q4** (attribution): Name who said or holds the preference. Do not name the foil.
- **Q5** (theory of mind): State the preference AND who knew/revealed it. Both parts required.
- **Q6** (norm vs individual): State whether the norm is truly universal or has exceptions, and name any exceptions.
- **Q7** (relational edge): Describe the relationship history as revealed in conversation.
- **Q8** (temporal shift): State the old preference, the new preference, and what triggered the change.
- **Q9** (departed member): State the departed member's last known preference as of their final session.

### 4. Score each answer (LLM-as-judge)

After answering ALL questions, go back and score each one by comparing `model_answer` to the `answer` field:

| Score | Meaning |
|-------|---------|
| 1.0 | Correct — same meaning, correct attribution, all required parts present |
| 0.7–0.9 | Mostly correct — right answer but one part missing or slightly imprecise |
| 0.4–0.6 | Partial — right direction but wrong detail, missing key element, or ambiguous attribution |
| 0.0–0.3 | Wrong — incorrect attribution, wrong preference, contradiction, or no answer |

Query-type scoring rules:
- **Q3**: score = fraction of group members correctly recalled (e.g., 3/5 correct = 0.6)
- **Q4**: must identify the correct speaker AND not name the foil → 1.0; correct speaker but also names foil → 0.7; wrong speaker → 0.0–0.3
- **Q5**: both parts (preference + who knew) must be correct for 1.0; only one part correct → 0.5
- **Q8**: both old AND new preference must be correct for 1.0; only one side correct → 0.5

Write a 1-sentence `score_rationale` for each pair explaining the score.

### 5. Build output

Per-pair result (one object per line in JSONL):
```json
{
  "qa_id": "...",
  "network_id": "...",
  "query_type": "Q1",
  "difficulty": "easy|medium|hard",
  "question": "...",
  "ground_truth": "...",
  "model_answer": "...",
  "score": 0.0,
  "score_rationale": "..."
}
```

Summary JSON:
```json
{
  "network_id": "...",
  "condition": "oracle",
  "evaluated_at": "{ISO 8601 timestamp}",
  "total_pairs": 0,
  "mean_score": 0.0,
  "by_query_type": {
    "Q1": {"count": 0, "mean_score": 0.0},
    "Q2": {"count": 0, "mean_score": 0.0},
    "Q3": {"count": 0, "mean_score": 0.0},
    "Q4": {"count": 0, "mean_score": 0.0},
    "Q5": {"count": 0, "mean_score": 0.0},
    "Q6": {"count": 0, "mean_score": 0.0},
    "Q7": {"count": 0, "mean_score": 0.0},
    "Q8": {"count": 0, "mean_score": 0.0}
  },
  "by_difficulty": {
    "easy":   {"count": 0, "mean_score": 0.0},
    "medium": {"count": 0, "mean_score": 0.0},
    "hard":   {"count": 0, "mean_score": 0.0}
  },
  "low_scoring": [
    {"qa_id": "...", "query_type": "...", "score": 0.0, "rationale": "..."}
  ]
}
```

### 6. Write files
- Create `data/results/oracle/` if it does not exist
- Write per-pair results to `data/results/oracle/{network_id}.jsonl`
- Write summary to `data/results/oracle/{network_id}_summary.json`
- Update `data/manifest.json`: set `networks.{network_id}.oracle_eval` to:
  ```json
  {
    "mean_score": 0.0,
    "total_pairs": 0,
    "evaluated_at": "{ISO 8601 timestamp}"
  }
  ```

### 7. Print summary
```
Oracle Eval: {network_id}
Total pairs: {n} | Mean score: {score:.2f}

By query type:
  Q1  {score:.2f}  ({n} pairs)
  Q2  {score:.2f}  ({n} pairs)
  Q3  {score:.2f}  ({n} pairs)
  Q4  {score:.2f}  ({n} pairs)
  Q5  {score:.2f}  ({n} pairs)
  Q6  {score:.2f}  ({n} pairs)
  Q7  {score:.2f}  ({n} pairs)
  Q8  {score:.2f}  ({n} pairs)

By difficulty:
  easy    {score:.2f}  ({n} pairs)
  medium  {score:.2f}  ({n} pairs)
  hard    {score:.2f}  ({n} pairs)

Low-scoring pairs (score < 0.50):
  {qa_id}  {query_type}  {score:.2f}  — {rationale}

Results: data/results/oracle/{network_id}_summary.json
```
