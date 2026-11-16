"""
Per-category 95% bootstrap CIs for every condition on the 43 evaluated networks.

Category scores in the paper are question-weighted means pooled over networks.
The CI resamples networks (not questions), since questions within a network
share a conversation corpus: each replicate draws, with replacement, from the
networks that contain at least one question of the category and pools their
questions. Writes data/results/category_bootstrap_cis.json and
data/results/tables/category_cis.csv (paper Table 16), and prints the table.
"""
import collections
import csv
import json

import numpy as np

from print_paper_numbers import CATS, CONDITIONS, NETS_ALL, QUERY_MAP, RESULTS_DIR, load_results

N_BOOT = 10000
SEED = 42
OUT_PATH = RESULTS_DIR / "category_bootstrap_cis.json"
CSV_PATH = RESULTS_DIR / "tables" / "category_cis.csv"


def main():
    results = {cond: category_cis(load_results(cond, NETS_ALL)) for cond in CONDITIONS}
    OUT_PATH.write_text(json.dumps(results, indent=2))
    write_csv(results)
    print_table(results)
    print(f"\nWrote {OUT_PATH}\nWrote {CSV_PATH}")


def category_cis(rows):
    by_cat_net = collections.defaultdict(lambda: collections.defaultdict(list))
    for _, nid, qtype, score in rows:
        by_cat_net[QUERY_MAP[qtype]][nid].append(float(score))
    return {cat: cluster_bootstrap(by_cat_net[cat]) for cat in CATS if by_cat_net[cat]}


def cluster_bootstrap(scores_by_net):
    """Question-weighted mean with a network-resampling percentile CI."""
    sums = np.array([sum(s) for s in scores_by_net.values()])
    counts = np.array([len(s) for s in scores_by_net.values()])
    rng = np.random.RandomState(SEED)
    idx = rng.randint(0, len(sums), size=(N_BOOT, len(sums)))
    boot = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    return {
        "mean": float(sums.sum() / counts.sum()),
        "ci_lo": float(np.percentile(boot, 2.5)),
        "ci_hi": float(np.percentile(boot, 97.5)),
        "n_questions": int(counts.sum()),
        "n_networks": int(len(sums)),
    }


def write_csv(results):
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["condition", "category", "mean", "ci_lo", "ci_hi", "n_questions", "n_networks"])
        for cond, cats in results.items():
            for cat in CATS:
                if cat in cats:
                    c = cats[cat]
                    w.writerow([cond, cat, f"{c['mean']:.4f}", f"{c['ci_lo']:.4f}", f"{c['ci_hi']:.4f}",
                                c["n_questions"], c["n_networks"]])


def print_table(results):
    print(f"{'condition':<12} " + " ".join(f"{c:>17}" for c in CATS))
    for cond, cats in results.items():
        cells = (
            f"{cats[c]['mean']:.2f} [{cats[c]['ci_lo']:.2f},{cats[c]['ci_hi']:.2f}]" if c in cats else "--"
            for c in CATS
        )
        print(f"{cond:<12} " + " ".join(f"{cell:>17}" for cell in cells))
    first = next(iter(results.values()))
    print("n (questions/networks): " + ", ".join(f"{c} {first[c]['n_questions']}/{first[c]['n_networks']}" for c in CATS if c in first))


if __name__ == "__main__":
    main()
