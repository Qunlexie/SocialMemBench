"""
Recompute bootstrap CIs and pairwise significance tests from current results.
Writes data/results/bootstrap_cis.json.
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
    # Newly evaluated small-tier networks (previously released but not evaluated)
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

# Small now includes the 4 DM networks (small-tier with departures)
NETS_SMALL = NETS_SMALL + NETS_DM

NETS_ALL = NETS_SMALL + NETS_MEDIUM + NETS_LARGE
NETS_WITH_DM = NETS_ALL  # DM already in NETS_SMALL

CONDITIONS = ["llm_mini", "naive_rag", "subject_rag", "smg",
              "graphiti", "langmem", "mem0_local", "cognee"]
N_BOOT = 10000


def load_per_network_means(condition: str, networks: list) -> dict:
    out = {}
    for nid in networks:
        pf = RESULTS_DIR / condition / f"{nid}.jsonl"
        if not pf.exists():
            continue
        scores = []
        for line in open(pf):
            if not line.strip():
                continue
            d = json.loads(line)
            scores.append(d.get("score", 0.0))
        if scores:
            out[nid] = float(np.mean(scores))
    return out


def bootstrap_ci(values: list, n_boot: int = N_BOOT, seed: int = 42):
    rng = np.random.RandomState(seed)
    arr = np.array(values)
    if len(arr) == 0:
        return {"mean": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"), "half": float("nan")}
    boot_means = np.zeros(n_boot)
    for i in range(n_boot):
        idx = rng.choice(len(arr), len(arr), replace=True)
        boot_means[i] = arr[idx].mean()
    mean = float(arr.mean())
    lo = float(np.percentile(boot_means, 2.5))
    hi = float(np.percentile(boot_means, 97.5))
    return {
        "mean": mean,
        "ci_lo": lo,
        "ci_hi": hi,
        "half": float((hi - lo) / 2),
    }


def pairwise_test(arr_a: np.ndarray, arr_b: np.ndarray, n_boot: int = N_BOOT, seed: int = 42):
    rng = np.random.RandomState(seed)
    n = len(arr_a)
    if n == 0 or n != len(arr_b):
        return {"p_one_sided": float("nan"), "obs_diff": float("nan")}
    diffs = np.zeros(n_boot)
    for i in range(n_boot):
        idx = rng.choice(n, n, replace=True)
        diffs[i] = arr_a[idx].mean() - arr_b[idx].mean()
    obs = float(arr_a.mean() - arr_b.mean())
    p = float((diffs <= 0).mean())
    return {"p_one_sided": p, "obs_diff": obs}


def main():
    # Per-condition CIs over the 27-network "all" set (the headline number)
    print("Computing CIs over 27 evaluated networks...")
    cis_all = {}
    for cond in CONDITIONS:
        per_net = load_per_network_means(cond, NETS_ALL)
        values = [per_net[n] for n in NETS_ALL if n in per_net]
        cis_all[cond] = {**bootstrap_ci(values), "n_networks": len(values)}
        print(f"  {cond}: mean={cis_all[cond]['mean']:.3f}  "
              f"CI=[{cis_all[cond]['ci_lo']:.3f}, {cis_all[cond]['ci_hi']:.3f}]  "
              f"n={cis_all[cond]['n_networks']}")

    # Including DM networks (when they're present)
    print("\nComputing CIs including DM networks (31 total)...")
    cis_with_dm = {}
    for cond in CONDITIONS:
        per_net = load_per_network_means(cond, NETS_WITH_DM)
        values = [per_net[n] for n in NETS_WITH_DM if n in per_net]
        cis_with_dm[cond] = {**bootstrap_ci(values), "n_networks": len(values)}
        print(f"  {cond}: mean={cis_with_dm[cond]['mean']:.3f}  "
              f"CI=[{cis_with_dm[cond]['ci_lo']:.3f}, {cis_with_dm[cond]['ci_hi']:.3f}]  "
              f"n={cis_with_dm[cond]['n_networks']}")

    # Pairwise significance tests on the 27-network set
    print(f"\nPairwise bootstrap p-values ({len(NETS_ALL)} networks, one-sided A > B):")
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
    pairwise = {}
    for a, b in pairs:
        per_a = load_per_network_means(a, NETS_ALL)
        per_b = load_per_network_means(b, NETS_ALL)
        common = sorted(set(per_a.keys()) & set(per_b.keys()))
        arr_a = np.array([per_a[n] for n in common])
        arr_b = np.array([per_b[n] for n in common])
        result = pairwise_test(arr_a, arr_b)
        pairwise[f"{a}_vs_{b}"] = result
        print(f"  {a} > {b}: obs_diff={result['obs_diff']:+.4f}, p={result['p_one_sided']:.4f}")

    # Save
    out = {
        "ci_27_networks": cis_all,
        "ci_with_dm": cis_with_dm,
        "pairwise_27_networks": pairwise,
    }
    out_path = RESULTS_DIR / "bootstrap_cis.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: {out_path}")

    # Also save a flat (legacy) version that the figure script reads
    legacy = {cond: cis_all[cond] for cond in CONDITIONS if cond in cis_all}
    legacy_path = RESULTS_DIR / "bootstrap_cis_legacy.json"
    with open(legacy_path, "w") as f:
        json.dump(legacy, f, indent=2)
    # Overwrite the main file with flat structure for figure compatibility
    with open(out_path, "w") as f:
        json.dump(legacy, f, indent=2)
    # Save the full structure separately
    full_path = RESULTS_DIR / "bootstrap_cis_full.json"
    with open(full_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Saved (legacy flat): {out_path}")
    print(f"Saved (full incl DM, pairwise): {full_path}")


if __name__ == "__main__":
    main()
