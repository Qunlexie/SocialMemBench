"""
Regenerate the ablation tables (paper Tables 13, 14, 15) from the ablation
result cells. Everything is read from data/results/ablation/, which is a single
self-contained evaluation run, so the numbers are internally consistent. They
are NOT spliced with the main-results run behind Table 4; the two runs are
separate evaluations and their absolute cells are not meant to be compared
one-for-one.

Outputs (tracked):
  data/results/tables/answerer_sweep.csv   (Table 13)
  data/results/tables/topk_sweep.csv       (Table 14)
  data/results/tables/extractor_swap.csv   (Table 15)

Each sweep cell reports both weightings:
  mean_q : question-weighted (pool all QA pairs)
  mean_n : network-weighted (mean of per-network means), with a 95% bootstrap
           CI over networks (the convention used in Table 4 / recompute_bootstrap.py).
Pure aggregation over existing cells; no API calls.
"""
import csv
import glob
import json
import os
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ABL = os.path.join(ROOT, "data", "results", "ablation")
OUT = os.path.join(ROOT, "data", "results", "tables")

CONDITIONS = ["llm_mini", "naive_rag", "subject_rag", "smg",
              "graphiti", "langmem", "mem0_local", "cognee"]
ANSWERERS = ["gpt-4o-mini", "gpt-4o", "gemini-2.5-flash"]
KS = [3, 5, 10]
N_BOOT = 10_000
SEED = 0
# Query-type code -> category (matches Table 2 / tab:query-types).
QCAT = {"Q1": "SR", "Q2": "GD", "Q3": "MA", "Q4": "AP", "Q5": "TM",
        "Q6": "NI", "Q7": "RE", "Q8": "TS", "Q9": "DM"}
CAT_ORDER = ["SR", "GD", "MA", "AP", "TM", "NI", "RE", "TS", "DM"]


def read_cell(cond, ans, k):
    """Return {network_id: [scores]} for one (cond, ans, k) cell."""
    by = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(ABL, cond, f"ans={ans}__k={k}", "*.jsonl"))):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            s = r.get("score")
            if isinstance(s, (int, float)):
                by[r.get("network_id", os.path.basename(f))].append(s)
    return by


def summarize(by):
    """Question- and network-weighted means with a per-cell seeded bootstrap CI."""
    all_scores = [s for v in by.values() for s in v]
    net_means = [float(np.mean(v)) for v in by.values() if v]
    if not all_scores:
        return dict(mean_q=float("nan"), mean_n=float("nan"),
                    ci_lo=float("nan"), ci_hi=float("nan"), n_q=0, n_net=0)
    arr = np.array(net_means)
    rng = np.random.RandomState(SEED)
    boot = np.array([arr[rng.choice(len(arr), len(arr), replace=True)].mean()
                     for _ in range(N_BOOT)])
    return dict(mean_q=float(np.mean(all_scores)),
                mean_n=float(arr.mean()),
                ci_lo=float(np.percentile(boot, 2.5)),
                ci_hi=float(np.percentile(boot, 97.5)),
                n_q=len(all_scores), n_net=len(net_means))


def write_sweep(path, prefix, cols, cell_fn):
    fields = ["condition"]
    for c in cols:
        fields += [f"{prefix}{c}_mean_q", f"{prefix}{c}_mean_n",
                   f"{prefix}{c}_ci_lo", f"{prefix}{c}_ci_hi", f"{prefix}{c}_n_net"]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for cond in CONDITIONS:
            row = {"condition": cond}
            for c in cols:
                s = summarize(cell_fn(cond, c))
                row[f"{prefix}{c}_mean_q"] = round(s["mean_q"], 4)
                row[f"{prefix}{c}_mean_n"] = round(s["mean_n"], 4)
                row[f"{prefix}{c}_ci_lo"] = round(s["ci_lo"], 4)
                row[f"{prefix}{c}_ci_hi"] = round(s["ci_hi"], 4)
                row[f"{prefix}{c}_n_net"] = s["n_net"]
            w.writerow(row)


def build_extractor(path):
    """Table 15: Graphiti extractor swap, per-category (question-weighted)."""
    by_cat_new = defaultdict(list)
    by_cat_base = defaultdict(list)
    by_net_new = defaultdict(list)
    by_net_base = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(ABL, "extractor_swap", "*.jsonl"))):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            s, b = r.get("score"), r.get("baseline_score")
            if not isinstance(s, (int, float)) or not isinstance(b, (int, float)):
                continue
            cat = QCAT.get(r.get("query_type", ""), r.get("query_type", "?"))
            net = r.get("network_id", os.path.basename(f))
            by_cat_new[cat].append(s)
            by_cat_base[cat].append(b)
            by_net_new[net].append(s)
            by_net_base[net].append(b)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["category", "n", "extractor_4o_mini", "extractor_4o", "delta"])
        for cat in CAT_ORDER:
            if cat not in by_cat_new:
                continue
            base = float(np.mean(by_cat_base[cat]))
            new = float(np.mean(by_cat_new[cat]))
            w.writerow([cat, len(by_cat_new[cat]), round(base, 4), round(new, 4),
                        round(new - base, 4)])
        allb = [x for v in by_net_base.values() for x in v]
        alln = [x for v in by_net_new.values() for x in v]
        w.writerow(["All (question-weighted)", len(alln),
                    round(float(np.mean(allb)), 4), round(float(np.mean(alln)), 4),
                    round(float(np.mean(alln) - np.mean(allb)), 4)])
        nb = float(np.mean([np.mean(v) for v in by_net_base.values()]))
        nn = float(np.mean([np.mean(v) for v in by_net_new.values()]))
        w.writerow(["All (network-weighted)", len(by_net_new),
                    round(nb, 4), round(nn, 4), round(nn - nb, 4)])


def preview():
    print("Answerer sweep (mean_q / mean_n +- half-CI), k=10:")
    for cond in CONDITIONS:
        cells = [summarize(read_cell(cond, a, 10)) for a in ANSWERERS]
        print(f"  {cond:<12} " + "  ".join(
            f"{c['mean_q']:.3f}/{c['mean_n']:.3f}+-{(c['ci_hi']-c['ci_lo'])/2:.3f}"
            for c in cells))


def main():
    os.makedirs(OUT, exist_ok=True)
    write_sweep(os.path.join(OUT, "answerer_sweep.csv"), "ans=",
                ANSWERERS, lambda cond, a: read_cell(cond, a, 10))
    write_sweep(os.path.join(OUT, "topk_sweep.csv"), "k=",
                KS, lambda cond, k: read_cell(cond, "gpt-4o-mini", k))
    build_extractor(os.path.join(OUT, "extractor_swap.csv"))
    print(f"wrote answerer_sweep.csv, topk_sweep.csv, extractor_swap.csv to "
          f"{os.path.relpath(OUT, ROOT)}/")
    preview()


if __name__ == "__main__":
    main()
