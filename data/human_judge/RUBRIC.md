# Human scoring guide (blinded)

Open http://localhost:8080/judge (start with `cd viewer && python3 server.py`) and mark
each system answer **Correct** or **Not correct** against the gold answer. This follows
LongMemEval's judge meta-evaluation (binary labels, percent agreement).

- **Correct**: gets the gold answer's core content right, with at most a minor detail
  missing or imprecise. Brevity is never penalised.
- **Not correct**: a key element wrong or missing, the wrong person, invented evidence,
  or no real answer ("NOT ENOUGH INFORMATION").
- Temporal shift: correct if both old and new state are right (trigger is a bonus).
- Theory of mind: correct only if both parts are right, including who revealed it with an
  observable action that matches the gold answer.
- Multi-person: correct if at least 70% of members are right.

These lines match the judge's rubric at its 0.7 threshold (rubric below). Do not open
`judge_key.csv` until every row is done, then run
`python3 scripts/human_judge_agreement.py analyze` from the repo root.

## Rubric (verbatim)

```
Score the generated answer against the gold answer on a 0.0–1.0 scale.

CRITICAL RULES (apply before all others):
1. A concise correct answer scores THE SAME as a verbose one. Do NOT penalize
   brevity or reward evidence citation. If the core fact is correct, score 1.0.
2. Attributing a fact to the wrong person is always a critical error → score ≤ 0.3,
   regardless of how much other content is correct.
3. "NOT ENOUGH INFORMATION" or "[No memories retrieved]" always scores 0.0.

General rubric:
- 1.0: Core fact correct, correct person/attribution, required parts present
- 0.7–0.9: Right answer but one minor part missing or slightly imprecise
- 0.4–0.6: Right direction but wrong detail, missing key element, or ambiguous
- 0.0–0.3: Wrong attribution, wrong fact, contradiction, or no answer

Q-type specific rules:
- Q1/Q3: Core fact + correct person = 1.0. Evidence citation is NOT required.
  For Q3, score = fraction of group members correctly recalled (e.g., 3/5 = 0.6).
- Q4 (attribution): Correct speaker named AND foil NOT named as answer → 1.0.
  Correct speaker + also names foil → 0.7. Wrong speaker → 0.0–0.3.
- Q5 (theory of mind): BOTH parts required for 1.0.
  Part 1 = correct preference/attitude.
  Part 2 = correctly names WHO revealed it AND identifies a specific observable
  action in the chat proving prior knowledge (e.g., an assumption made without
  asking, a knowing callback, finishing someone's thought).
  A claimed private conversation satisfies Part 2 only if chat behavior
  in the transcript corroborates it.
  One part correct → 0.5. Neither → 0.0–0.3.
- Q8 (temporal shift): old state correct (+0.33) + new state correct (+0.33)
  + trigger/mechanism identified (+0.33) = 1.0.
  Both states, no trigger → 0.7. One state only → 0.4. Neither → 0.0–0.2.


```
