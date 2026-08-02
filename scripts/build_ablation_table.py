"""
Aggregate ablation results into two CSV artifacts:

  data/results/ablation/answerer_sweep_table.csv
  data/results/ablation/topk_sweep_table.csv

Tables for the paper are written by hand from these CSVs; this script does
not emit LaTeX.

Sources
- Ablation results:  data/results/ablation/{cond}/ans={ans}__k={k}/{net}.jsonl
- Baseline results:  data/results/{cond}/{net}.jsonl  (treated as ans=gpt-4o-mini, k=10)

Baseline is loaded so the two tables include the reference cell without any
extra runs. Baseline files are read-only for this script; nothing under
`data/results/{cond}/` is written or modified.

Bootstrap CIs are 95% percentile over N_BOOT resamples of the per-network mean.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "data" / "results"
ABLATION_ROOT = RESULTS_DIR / "ablation"

# Small-tier headline network set (matches scripts/recompute_bootstrap.py NETS_SMALL
# minus the DM networks, which are structurally different).
NETS_SMALL = [
    "grp_0d1e2f3a", "grp_1a2b3c4d", "grp_2b3c4d5e", "grp_3c4d5e6f",
    "grp_4d5e6f7a", "grp_5e6f7a8b", "grp_6f7a8b9c", "grp_7a8b9c0d",
    "grp_8b9c0d1e", "grp_9c0d1e2f",
    "grp_a9b0c1d2", "grp_c1d2e3f4", "grp_d4e5f6a7", "grp_e6f7a8b9", "grp_f7a8b9c0",
]

CONDITIONS = ["llm_mini", "naive_rag", "subject_rag", "smg",
              "graphiti", "langmem", "mem0_local", "cognee"]

# Pretty labels for the paper.
COND_LABEL = {
    "llm_mini": "\\textsc{Llm-Mini} (oracle)",
    "naive_rag": "Naive-RAG",
    "subject_rag": "Subject-RAG",
    "smg": "SMG",
    "graphiti": "Graphiti",
    "langmem": "LangMem",
    "mem0_local": "Mem0",
    "cognee": "Cognee",
}

# Baseline is (ans=gpt-4o-mini, k=10). Sweep columns reference it.
BASELINE_ANS = "gpt-4o-mini"
BASELINE_K = 10

ANSWERERS_ORDER = ["gpt-4o-mini", "gpt-4o", "gemini-2.5-flash"]
KS_ORDER = [3, 5, 10, 20, 50, 10000]  # 10000 stands in for "k=all"
K_LABEL = {3: "3", 5: "5", 10: "10", 20: "20", 50: "50", 10000: "all"}

N_BOOT = 10_000
OUT_ANS_CSV = ABLATION_ROOT / "answerer_sweep_table.csv"
OUT_K_CSV = ABLATION_ROOT / "topk_sweep_table.csv"


def load_jsonl_mean(path: Path) -> float:
    scores = []
    if not path.exists():
        return float("nan")
    with open(path) as f:
        for line in f:
            if line.strip():
                scores.append(json.loads(line).get("score", 0.0))
    return float(np.mean(scores)) if scores else float("nan")


def per_network_means(condition: str, answerer: str, top_k: int) -> dict:
    """Return {network_id: mean_score} for a given (cond, ans, k) cell."""
    out = {}
    if answerer == BASELINE_ANS and top_k == BASELINE_K:
        # Baseline: read from data/results/{cond}/{net}.jsonl (paper-cited).
        for net in NETS_SMALL:
            m = load_jsonl_mean(RESULTS_DIR / condition / f"{net}.jsonl")
            if not np.isnan(m):
                out[net] = m
    else:
        cell_dir = ABLATION_ROOT / condition / f"ans={answerer}__k={top_k}"
        for net in NETS_SMALL:
            m = load_jsonl_mean(cell_dir / f"{net}.jsonl")
            if not np.isnan(m):
                out[net] = m
    return out


def bootstrap_ci(values: list, n_boot: int = N_BOOT, seed: int = 42) -> dict:
    arr = np.array(values)
    if len(arr) == 0:
        return {"mean": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"), "n": 0}
    rng = np.random.RandomState(seed)
    boot_means = np.zeros(n_boot)
    for i in range(n_boot):
        idx = rng.choice(len(arr), len(arr), replace=True)
        boot_means[i] = arr[idx].mean()
    return {
        "mean": float(arr.mean()),
        "ci_lo": float(np.percentile(boot_means, 2.5)),
        "ci_hi": float(np.percentile(boot_means, 97.5)),
        "n": len(arr),
    }


def collect_cell(condition: str, answerer: str, top_k: int) -> dict:
    pn = per_network_means(condition, answerer, top_k)
    values = [pn[n] for n in NETS_SMALL if n in pn]
    return bootstrap_ci(values)


def build_answerer_table():
    """Rows = conditions; columns = answerers at k=10."""
    rows = []
    for cond in CONDITIONS:
        row = {"condition": cond, "label": COND_LABEL[cond]}
        for ans in ANSWERERS_ORDER:
            ci = collect_cell(cond, ans, BASELINE_K)
            row[ans] = ci
        rows.append(row)
    return rows


def build_topk_table():
    """Rows = conditions; columns = k at fixed answerer=gpt-4o-mini."""
    rows = []
    for cond in CONDITIONS:
        row = {"condition": cond, "label": COND_LABEL[cond]}
        for k in KS_ORDER:
            ci = collect_cell(cond, BASELINE_ANS, k)
            row[k] = ci
        rows.append(row)
    return rows


def write_answerer_csv(rows):
    fields = ["condition"]
    for a in ANSWERERS_ORDER:
        fields += [f"{a}_mean", f"{a}_ci_lo", f"{a}_ci_hi", f"{a}_n"]
    with open(OUT_ANS_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            out = {"condition": r["condition"]}
            for a in ANSWERERS_ORDER:
                ci = r[a]
                out[f"{a}_mean"] = ci["mean"]
                out[f"{a}_ci_lo"] = ci["ci_lo"]
                out[f"{a}_ci_hi"] = ci["ci_hi"]
                out[f"{a}_n"] = ci["n"]
            w.writerow(out)


def write_topk_csv(rows):
    fields = ["condition"]
    for k in KS_ORDER:
        fields += [f"k={K_LABEL[k]}_mean", f"k={K_LABEL[k]}_ci_lo",
                   f"k={K_LABEL[k]}_ci_hi", f"k={K_LABEL[k]}_n"]
    with open(OUT_K_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            out = {"condition": r["condition"]}
            for k in KS_ORDER:
                ci = r[k]
                lbl = K_LABEL[k]
                out[f"k={lbl}_mean"] = ci["mean"]
                out[f"k={lbl}_ci_lo"] = ci["ci_lo"]
                out[f"k={lbl}_ci_hi"] = ci["ci_hi"]
                out[f"k={lbl}_n"] = ci["n"]
            w.writerow(out)


def preview(rows, col_keys, col_labels, title):
    print(f"\n{title}")
    header = f"{'condition':<28}" + "".join(f"{lbl:>10}" for lbl in col_labels)
    print(header)
    print("-" * len(header))
    for r in rows:
        line = f"{r['condition']:<28}"
        for k in col_keys:
            ci = r[k]
            cell = "--" if ci["n"] == 0 or np.isnan(ci["mean"]) else f"{ci['mean']:.3f}"
            line += f"{cell:>10}"
        print(line)


def main():
    ans_rows = build_answerer_table()
    k_rows = build_topk_table()

    write_answerer_csv(ans_rows)
    write_topk_csv(k_rows)

    print(f"Wrote {OUT_ANS_CSV.relative_to(ROOT)}")
    print(f"Wrote {OUT_K_CSV.relative_to(ROOT)}")

    preview(ans_rows, ANSWERERS_ORDER, ANSWERERS_ORDER,
            "Answerer sweep (k=10):")
    preview(k_rows, KS_ORDER, [K_LABEL[k] for k in KS_ORDER],
            "Top-k sweep (ans=gpt-4o-mini):")


if __name__ == "__main__":
    main()
