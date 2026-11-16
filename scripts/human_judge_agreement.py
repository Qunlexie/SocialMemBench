"""
Human-judge agreement on a blinded sample of saved, judge-scored answers.

  python scripts/human_judge_agreement.py sample    # writes the blind sheet + hidden key
  python scripts/human_judge_agreement.py context   # per-item evidence + question type for the judge page
  python scripts/human_judge_agreement.py analyze   # after the sheet is filled in

`sample` draws a seeded sample of open-ended answers spread across the eight
conditions and the judge's rubric bands, so agreement is not dominated by
easy zeros. The annotation sheet shows only question, gold answer and system
answer; condition, judge score and rationale go to a separate key file that
the annotator should not open. `analyze` follows LongMemEval's judge meta-evaluation: both human and judge
scores are turned into correct / not correct at 0.7 (the rubric's line between
"right answer, at most a minor part missing" and partial or wrong), and it
reports percent agreement and Cohen's kappa with bootstrap 95% intervals.
"""
import collections
import csv
import json
import random
import sys
from pathlib import Path

import numpy as np

from print_paper_numbers import CONDITIONS, NETS_ALL, QUERY_MAP, RESULTS_DIR

ROOT = RESULTS_DIR.parent.parent
OUT_DIR = ROOT / "data" / "human_judge"
SHEET = OUT_DIR / "annotation_sheet.csv"
KEY = OUT_DIR / "judge_key.csv"
# Gold-side context only (question type, evidence anchors); no condition or judge score.
CONTEXT = OUT_DIR / "item_context.json"
PILOT_ITEMS = 20   # H001-H020: pilot used to refine the annotation interface
MAIN_ITEMS = 50    # H021-H070: the reported set, fixed before annotation
SAMPLE_SIZE = 100
SEED = 2027
OPEN_ENDED = {"long_form", "short_answer"}
# Removed from the release after evaluation (paper Appendix C.4).
EXCLUDED = {("grp_d2e3f4a5", "Q2_e4f5a6b7"), ("grp_d2e3f4a5", "Q7_5d3a7b1e")}
BAND_EDGES = (0.35, 0.65, 0.95)  # rubric bands used to stratify the sample
CORRECT_AT = 0.7  # rubric: 0.7-1.0 = right answer, at most a minor part missing


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "sample":
        write_sample()
    elif command == "context":
        write_context()
    elif command == "analyze":
        analyze()
    else:
        sys.exit(__doc__)


def write_sample():
    answers = load_open_ended_answers()
    picked = stratified_sample(answers)
    random.Random(SEED).shuffle(picked)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(SHEET, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", "question", "gold_answer", "system_answer", "human_score", "notes"])
        for i, a in enumerate(picked, 1):
            w.writerow([f"H{i:03d}", a["question"], a["gold"], a["answer"], "", ""])
    with open(KEY, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", "network_id", "qa_id", "category", "condition", "judge_score"])
        for i, a in enumerate(picked, 1):
            w.writerow([f"H{i:03d}", a["network_id"], a["qa_id"], a["category"], a["condition"], a["judge"]])
    bands = collections.Counter(band(a["judge"]) for a in picked)
    print(f"Wrote {len(picked)} items to {SHEET}\nKey (keep closed): {KEY}\nJudge bands in sample: {dict(sorted(bands.items()))}")


def write_context():
    qa = {}
    for path in (ROOT / "data" / "qa").glob("grp_*.jsonl"):
        for line in open(path):
            if line.strip():
                q = json.loads(line)
                qa[(q["network_id"], q["qa_id"])] = q
    with open(KEY) as f:
        key = list(csv.DictReader(f))
    context = {}
    for row in key:
        q = qa[(row["network_id"], row["qa_id"])]
        context[row["item"]] = {
            "category": row["category"],
            "anchors": [
                {k: a.get(k) for k in ("session_index", "speaker_display_name", "message_excerpt", "relevance")}
                for a in q.get("evidence_anchors") or []
            ],
        }
    CONTEXT.write_text(json.dumps(context, indent=1))
    print(f"Wrote gold-side context for {len(context)} items to {CONTEXT}")


def load_open_ended_answers():
    qa_meta = {}
    for path in (ROOT / "data" / "qa").glob("grp_*.jsonl"):
        for line in open(path):
            if line.strip():
                q = json.loads(line)
                qa_meta[(q["network_id"], q["qa_id"])] = q
    answers = []
    for condition in CONDITIONS:
        for nid in NETS_ALL:
            path = RESULTS_DIR / condition / f"{nid}.jsonl"
            if not path.exists():
                continue
            for line in open(path):
                if not line.strip():
                    continue
                r = json.loads(line)
                key = (r["network_id"], r["qa_id"])
                q = qa_meta.get(key)
                if key in EXCLUDED or q is None or q["answer_format"] not in OPEN_ENDED:
                    continue
                answers.append({
                    "network_id": r["network_id"], "qa_id": r["qa_id"],
                    "category": QUERY_MAP[r["query_type"]], "condition": condition,
                    "question": q["question"], "gold": q["answer"],
                    "answer": r["generated_answer"], "judge": float(r["score"]),
                })
    return answers


def stratified_sample(answers):
    """Equal share per condition, spread across judge bands within each condition."""
    rng = random.Random(SEED)
    cells = collections.defaultdict(list)
    for a in answers:
        cells[(a["condition"], band(a["judge"]))].append(a)
    per_condition = SAMPLE_SIZE // len(CONDITIONS)
    extra = SAMPLE_SIZE - per_condition * len(CONDITIONS)
    picked = []
    for ci, condition in enumerate(CONDITIONS):
        quota = per_condition + (1 if ci < extra else 0)
        pools = [rng.sample(cells[(condition, b)], len(cells[(condition, b)])) for b in range(4)]
        # round-robin over bands so sparse bands still contribute
        while quota and any(pools):
            for pool in pools:
                if quota and pool:
                    picked.append(pool.pop())
                    quota -= 1
    return picked


def analyze():
    human = {}
    with open(SHEET) as f:
        for row in csv.DictReader(f):
            if row["human_score"].strip():
                human[row["item"]] = float(row["human_score"])
    with open(KEY) as f:
        key = {row["item"]: row for row in csv.DictReader(f)}
    item_no = lambda item: int(item[1:])
    sets = {
        f"Pilot (H001-H{PILOT_ITEMS:03d})": [i for i in human if item_no(i) <= PILOT_ITEMS],
        f"Main set (H{PILOT_ITEMS + 1:03d}-H{PILOT_ITEMS + MAIN_ITEMS:03d}), reported": [
            i for i in human if PILOT_ITEMS < item_no(i) <= PILOT_ITEMS + MAIN_ITEMS],
    }
    for name, items in sets.items():
        print(f"\n== {name}: {len(items)} scored")
        if items:
            report(sorted(items), human, key)


def report(items, human, key):
    h = np.array([human[i] >= CORRECT_AT for i in items], dtype=int)
    j = np.array([float(key[i]["judge_score"]) >= CORRECT_AT for i in items], dtype=int)
    agree, kappa = agreement(h, j)
    agree_ci, kappa_ci = bootstrap_ci(h, j)
    print(f"human marks {h.mean():.0%} correct, judge {j.mean():.0%}")
    print(f"Agreement on correct / not correct: {agree:.1%}  (95% CI {agree_ci[0]:.1%} to {agree_ci[1]:.1%})")
    print(f"Cohen's kappa:                      {kappa:.2f}   (95% CI {kappa_ci[0]:.2f} to {kappa_ci[1]:.2f})")
    print(f"Disagreements: human correct / judge not = {int(((h == 1) & (j == 0)).sum())}, "
          f"human not / judge correct = {int(((h == 0) & (j == 1)).sum())}")


def agreement(h, j):
    observed = np.mean(h == j)
    expected = h.mean() * j.mean() + (1 - h.mean()) * (1 - j.mean())
    kappa = (observed - expected) / (1 - expected) if expected < 1 else float("nan")
    return observed, kappa


def bootstrap_ci(h, j, n_boot=10000):
    rng = np.random.default_rng(SEED)
    draws = [agreement(h[idx], j[idx]) for idx in rng.integers(0, len(h), (n_boot, len(h)))]
    agrees = [a for a, _ in draws]
    kappas = [k for _, k in draws if not np.isnan(k)]
    pct = lambda xs: (np.percentile(xs, 2.5), np.percentile(xs, 97.5))
    return pct(agrees), pct(kappas)


def band(score):
    return sum(score > edge for edge in BAND_EDGES)


if __name__ == "__main__":
    main()
