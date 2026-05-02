"""
Print all the headline numbers needed to update the paper.

Reads from data/results/{condition}/{network_id}.jsonl and computes:
- Per-condition mean^Q (question-weighted) on 27 evaluated networks
- Per-condition mean^N (network-weighted) with bootstrap CIs
- Per-category means (heatmap rows)
- Per-tier means
- Pairwise significance tests
- DM scores (if evaluated)
"""
import json
import os
import collections
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "data" / "results"

NETS_SMALL = [
    "grp_0d1e2f3a", "grp_1a2b3c4d", "grp_2b3c4d5e", "grp_3c4d5e6f",
    "grp_4d5e6f7a", "grp_5e6f7a8b", "grp_6f7a8b9c", "grp_7a8b9c0d",
    "grp_8b9c0d1e", "grp_9c0d1e2f",
    "grp_a9b0c1d2", "grp_c1d2e3f4", "grp_d4e5f6a7", "grp_e6f7a8b9", "grp_f7a8b9c0",
]
NETS_MEDIUM = [
    "grp_a0b1c2d3", "grp_a1b2c3d4", "grp_a3b4c5d6", "grp_a5b6c7d8",
    "grp_b0c1d2e3", "grp_b2c3d4e5", "grp_b6c7d8e9", "grp_c2d3e4f5",
    "grp_c3d4e5f6", "grp_d2e3f4a5", "grp_dba9214c", "grp_e8f9a0b1",
    "grp_f2e3d4c5", "grp_f9a0b1c2",
]
NETS_LARGE_ORIG = ["grp_b1c2d3e4", "grp_e5f6a7b8", "grp_f6g7h8i9"]
NETS_LARGE_NEW = ["grp_a4b5c6d7", "grp_b8c9dae0", "grp_c1d2e3f7", "grp_d3e4f5a6",
                  "grp_e7f8a9b1", "grp_f1a2b3c5", "grp_a6b7c8d9"]
NETS_LARGE = NETS_LARGE_ORIG + NETS_LARGE_NEW
NETS_DM = ["grp_c6d7e8f9", "grp_d7e8f9a0", "grp_e3f4a5b6", "grp_f4a5b6c7"]

# Small-tier now includes the 4 DM networks (small with departures)
NETS_SMALL = NETS_SMALL + NETS_DM

NETS_ALL = NETS_SMALL + NETS_MEDIUM + NETS_LARGE  # 38 evaluated networks
CONDITIONS = ["llm_mini", "naive_rag", "subject_rag", "smg",
              "graphiti", "langmem", "mem0_local", "cognee"]
GEMINI = "llm_gemini"

QUERY_MAP = {"Q1": "SR", "Q2": "GD", "Q3": "MA", "Q4": "AP",
             "Q5": "TM", "Q6": "NI", "Q7": "RE", "Q8": "TS", "Q9": "DM"}
CATS = ["SR", "GD", "MA", "AP", "TM", "NI", "RE", "TS", "DM"]


def load_results(condition: str, networks: list):
    """Returns list of (qa_id, network_id, query_type, score)."""
    rows = []
    for nid in networks:
        pf = RESULTS_DIR / condition / f"{nid}.jsonl"
        if not pf.exists():
            continue
        for line in open(pf):
            if not line.strip():
                continue
            d = json.loads(line)
            rows.append((d.get("qa_id"), nid, d.get("query_type"), d.get("score", 0.0)))
    return rows


def per_network_mean(rows):
    by_net = collections.defaultdict(list)
    for _, nid, _, s in rows:
        by_net[nid].append(s)
    return {n: float(np.mean(ss)) for n, ss in by_net.items()}


def bootstrap_ci(values, n_boot=10000, seed=42):
    rng = np.random.RandomState(seed)
    if not values:
        return float("nan"), float("nan"), float("nan")
    arr = np.array(values)
    boot = np.zeros(n_boot)
    for i in range(n_boot):
        idx = rng.choice(len(arr), len(arr), replace=True)
        boot[i] = arr[idx].mean()
    return float(arr.mean()), float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def main():
    print("=" * 78)
    print("HEADLINE NUMBERS — 27 evaluated networks + 4 DM networks")
    print("=" * 78)

    print("\n## Mean^Q (question-weighted) and Mean^N (network-weighted, with 95% CI)")
    print("Networks evaluated: 27 (excluding DM-only networks)\n")
    print(f'{"Condition":<14} {"Mean^Q":>8} {"Mean^N":>8} {"CI_lo":>7} {"CI_hi":>7} {"±half":>6} {"n":>3}')

    cond_data_27 = {}
    for cond in CONDITIONS:
        rows = load_results(cond, NETS_ALL)
        if not rows:
            print(f"{cond:<14}  -- no results --")
            continue
        all_scores = [s for _, _, _, s in rows]
        per_net = per_network_mean(rows)
        net_means = list(per_net.values())
        mean_n, ci_lo, ci_hi = bootstrap_ci(net_means)
        mean_q = float(np.mean(all_scores))
        half = (ci_hi - ci_lo) / 2 if ci_hi > 0 else 0
        cond_data_27[cond] = {"mean_q": mean_q, "mean_n": mean_n, "ci_lo": ci_lo, "ci_hi": ci_hi, "half": half, "n": len(per_net)}
        print(f"{cond:<14} {mean_q:>8.3f} {mean_n:>8.3f} {ci_lo:>7.3f} {ci_hi:>7.3f} {half:>6.3f} {len(per_net):>3}")

    print("\n## Per-category Mean^Q (heatmap rows, 27 evaluated networks)\n")
    print(f'{"Cond":<14} ' + " ".join(f"{c:>5}" for c in CATS))
    cat_data_27 = {}
    for cond in CONDITIONS:
        rows = load_results(cond, NETS_ALL)
        by_cat = collections.defaultdict(list)
        for _, _, qt, s in rows:
            cat = QUERY_MAP.get(qt)
            if cat:
                by_cat[cat].append(s)
        cat_means = {cat: float(np.mean(by_cat.get(cat, [float("nan")]))) if by_cat.get(cat) else float("nan") for cat in CATS}
        cat_data_27[cond] = cat_means
        line = f"{cond:<14} " + " ".join(f"{cat_means.get(c, float('nan')):>5.2f}" if not np.isnan(cat_means.get(c, float('nan'))) else "  -- " for c in CATS)
        print(line)

    # Gemini (small-tier only)
    print()
    rows = load_results(GEMINI, NETS_SMALL)
    if rows:
        all_scores = [s for _, _, _, s in rows]
        mean_q = float(np.mean(all_scores))
        per_net = per_network_mean(rows)
        net_means = list(per_net.values())
        mean_n, _, _ = bootstrap_ci(net_means)
        print(f"## llm_gemini (small-tier only): Mean^Q={mean_q:.3f}, Mean^N={mean_n:.3f}, n={len(per_net)}")

    # Per-tier
    print("\n## Per-tier means (question-weighted)")
    print(f'{"Cond":<14} {"Small":>7} {"Medium":>7} {"Large":>7} {"DM":>7}')
    for cond in CONDITIONS:
        small = load_results(cond, NETS_SMALL)
        medium = load_results(cond, NETS_MEDIUM)
        large = load_results(cond, NETS_LARGE)
        dm = load_results(cond, NETS_DM)
        s_m = float(np.mean([s for _, _, _, s in small])) if small else float("nan")
        m_m = float(np.mean([s for _, _, _, s in medium])) if medium else float("nan")
        l_m = float(np.mean([s for _, _, _, s in large])) if large else float("nan")
        dm_m = float(np.mean([s for _, _, _, s in dm])) if dm else float("nan")
        def fmt(x): return f"{x:.3f}" if not np.isnan(x) else "  -- "
        print(f"{cond:<14} {fmt(s_m):>7} {fmt(m_m):>7} {fmt(l_m):>7} {fmt(dm_m):>7}")

    # Per-tier graphiti collapse on TS, NI, RE
    print("\n## Graphiti large-tier per-category (for collapse claim)")
    rows = load_results("graphiti", NETS_LARGE)
    by_cat = collections.defaultdict(list)
    for _, _, qt, s in rows:
        cat = QUERY_MAP.get(qt)
        if cat:
            by_cat[cat].append(s)
    for cat in CATS:
        vals = by_cat.get(cat, [])
        m = float(np.mean(vals)) if vals else float("nan")
        n = len(vals)
        if not np.isnan(m):
            print(f"  Graphiti large-tier {cat}: {m:.3f} (n={n})")

    # Pairwise tests on 27 networks
    print("\n## Pairwise bootstrap p-values (one-sided A > B, 27 networks)")
    pairs = [
        ("subject_rag", "graphiti"),
        ("subject_rag", "langmem"),
        ("smg", "graphiti"),
        ("smg", "langmem"),
        ("graphiti", "langmem"),
        ("langmem", "mem0_local"),
        ("mem0_local", "cognee"),
        ("naive_rag", "subject_rag"),
    ]
    for a, b in pairs:
        per_a = per_network_mean(load_results(a, NETS_ALL))
        per_b = per_network_mean(load_results(b, NETS_ALL))
        common = sorted(set(per_a.keys()) & set(per_b.keys()))
        if not common:
            continue
        arr_a = np.array([per_a[n] for n in common])
        arr_b = np.array([per_b[n] for n in common])
        rng = np.random.RandomState(42)
        diffs = []
        for _ in range(10000):
            idx = rng.choice(len(common), len(common), replace=True)
            diffs.append(arr_a[idx].mean() - arr_b[idx].mean())
        p = float((np.array(diffs) <= 0).mean())
        obs = float(arr_a.mean() - arr_b.mean())
        print(f"  {a:<12} > {b:<12}: obs_diff={obs:+.4f}, p={p:.4f}")

    # DM tier results
    print("\n## DM scores by condition (4 DM networks)")
    print(f'{"Cond":<14} {"Mean":>8} {"DM-only":>8}')
    for cond in CONDITIONS:
        rows = load_results(cond, NETS_DM)
        if not rows:
            print(f"{cond:<14}   not evaluated")
            continue
        m_all = float(np.mean([s for _, _, _, s in rows]))
        dm_only = [s for _, _, qt, s in rows if qt == "Q9"]
        m_dm = float(np.mean(dm_only)) if dm_only else float("nan")
        print(f"{cond:<14} {m_all:>8.3f} {m_dm:>8.3f}")


if __name__ == "__main__":
    main()
