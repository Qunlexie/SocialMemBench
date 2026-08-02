"""
Sensitivity analysis of the per-QA blind-critic answerability threshold.

For a grid of thresholds tau, filter QA pairs to {qa : qc_phase1_score >= tau}
and report:
  (a) Coverage retention (overall, by query type, by tier)
  (b) Per-network mean-score dropout
  (c) Per-condition mean accuracy on the retained subset
  (d) Rank stability (Kendall tau) of condition ordering vs. baseline

Outputs a single JSON to data/verify/sensitivity_qc_threshold.json and prints
a summary table suitable for the rebuttal.

Analysis only. Does not modify any data or paper file.
"""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import kendalltau

ROOT = Path(__file__).parent.parent
QA_DIR = ROOT / "data" / "qa"
RAW_DIR = ROOT / "data" / "raw"
RESULTS_DIR = ROOT / "data" / "results"
OUT_PATH = ROOT / "data" / "verify" / "sensitivity_qc_threshold.json"

CONDITIONS = [
    "llm_mini", "naive_rag", "subject_rag", "smg",
    "graphiti", "langmem", "mem0_local", "cognee",
]

TAUS = [0.00, 0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.99]
MEAN_GATES = [0.70, 0.75, 0.80, 0.85, 0.86, 0.87, 0.88, 0.90, 0.92, 0.95]


def is_icloud_dup(path: Path) -> bool:
    # iCloud writes conflicting copies as "name 2.ext"
    return " 2" in path.stem


def tier_from_size(n: int) -> str:
    if n <= 6:
        return "small"
    if n <= 14:
        return "medium"
    return "large"


def load_network_tiers() -> dict:
    """Return {network_id: tier} using persona count from data/raw/."""
    tiers = {}
    for p in RAW_DIR.glob("grp_*.json"):
        if is_icloud_dup(p):
            continue
        try:
            d = json.load(open(p))
        except Exception:
            continue
        n = d.get("group_size") or len(d.get("personas", []))
        if n:
            tiers[p.stem] = tier_from_size(int(n))
    return tiers


def load_qa_scores() -> list:
    """Load per-QA rows: {qa_id, network_id, query_type, qc_phase1_score}."""
    rows = []
    for p in QA_DIR.glob("grp_*.jsonl"):
        if is_icloud_dup(p) or "_qc" in p.stem:
            continue
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            s = d.get("qc_phase1_score")
            if s is None:
                continue
            rows.append({
                "qa_id": d["qa_id"],
                "network_id": d["network_id"],
                "query_type": d.get("query_type", ""),
                "qc_phase1_score": float(s),
            })
    return rows


def load_condition_scores(condition: str) -> dict:
    """Return {qa_id: score} for a condition, across all networks."""
    cdir = RESULTS_DIR / condition
    if not cdir.exists():
        return {}
    out = {}
    for p in cdir.glob("grp_*.jsonl"):
        if is_icloud_dup(p) or p.stem.endswith("_summary"):
            continue
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            qid = d.get("qa_id")
            s = d.get("score")
            if qid is None or s is None:
                continue
            out[qid] = float(s)
    return out


def coverage_at_tau(qa_rows: list, tau: float) -> dict:
    """Coverage retained at threshold tau, overall / by query type / by tier."""
    total = len(qa_rows)
    kept = [r for r in qa_rows if r["qc_phase1_score"] >= tau]
    by_qt_kept = defaultdict(int)
    by_qt_total = defaultdict(int)
    by_tier_kept = defaultdict(int)
    by_tier_total = defaultdict(int)
    for r in qa_rows:
        by_qt_total[r["query_type"]] += 1
        by_tier_total[r["tier"]] += 1
        if r["qc_phase1_score"] >= tau:
            by_qt_kept[r["query_type"]] += 1
            by_tier_kept[r["tier"]] += 1
    return {
        "tau": tau,
        "kept": len(kept),
        "total": total,
        "retention": len(kept) / total if total else 0.0,
        "by_query_type": {
            qt: {
                "kept": by_qt_kept[qt],
                "total": by_qt_total[qt],
                "retention": by_qt_kept[qt] / by_qt_total[qt] if by_qt_total[qt] else 0.0,
            }
            for qt in sorted(by_qt_total)
        },
        "by_tier": {
            t: {
                "kept": by_tier_kept[t],
                "total": by_tier_total[t],
                "retention": by_tier_kept[t] / by_tier_total[t] if by_tier_total[t] else 0.0,
            }
            for t in sorted(by_tier_total)
        },
    }


def per_network_mean(qa_rows: list) -> dict:
    """{network_id: mean qc_phase1_score}."""
    buckets = defaultdict(list)
    for r in qa_rows:
        buckets[r["network_id"]].append(r["qc_phase1_score"])
    return {nid: float(np.mean(v)) for nid, v in buckets.items()}


def network_dropout(per_net_means: dict, gate: float) -> dict:
    dropped = [nid for nid, m in per_net_means.items() if m < gate]
    return {
        "gate": gate,
        "dropped_count": len(dropped),
        "kept_count": len(per_net_means) - len(dropped),
        "dropped_networks": sorted(dropped),
    }


def condition_accuracy_at_tau(
    qa_rows: list, cond_scores: dict, tau: float
) -> dict:
    """Mean accuracy for a condition on {qa: qc_phase1_score >= tau}.
    Only includes pairs that have both a QC score and a condition score."""
    scores = []
    by_qt = defaultdict(list)
    for r in qa_rows:
        if r["qc_phase1_score"] < tau:
            continue
        s = cond_scores.get(r["qa_id"])
        if s is None:
            continue
        scores.append(s)
        by_qt[r["query_type"]].append(s)
    return {
        "n": len(scores),
        "mean": float(np.mean(scores)) if scores else float("nan"),
        "by_query_type": {
            qt: {"n": len(vs), "mean": float(np.mean(vs))}
            for qt, vs in sorted(by_qt.items())
        },
    }


def rank_stability(cond_means_by_tau: dict, baseline_tau: float) -> dict:
    """Kendall tau between condition ranking at baseline_tau vs. every other tau."""
    conds = sorted(cond_means_by_tau[baseline_tau].keys())
    baseline = [cond_means_by_tau[baseline_tau][c] for c in conds]
    out = {}
    for tau, means in sorted(cond_means_by_tau.items()):
        this = [means[c] for c in conds]
        if any(np.isnan(x) for x in this) or any(np.isnan(x) for x in baseline):
            out[str(tau)] = {"kendall_tau": float("nan"), "p_value": float("nan"),
                             "n_conditions": sum(1 for x in this if not np.isnan(x))}
            continue
        tau_stat, p = kendalltau(baseline, this)
        out[str(tau)] = {"kendall_tau": float(tau_stat), "p_value": float(p),
                         "n_conditions": len(this)}
    return out


def per_category_rank_stability(
    qa_rows: list, cond_scores_by: dict, taus: list, baseline_tau: float
) -> dict:
    """Per-query-type Kendall tau across thresholds.
    Returns {query_type: {tau: {kendall_tau, p_value, n_pairs}}}."""
    conds = sorted(cond_scores_by.keys())
    qtypes = sorted({r["query_type"] for r in qa_rows if r["query_type"]})
    out = {}
    for qt in qtypes:
        qt_rows = [r for r in qa_rows if r["query_type"] == qt]
        means_by_tau = {}
        n_by_tau = {}
        for tau in taus:
            means_by_tau[tau] = {}
            kept_qa = [r for r in qt_rows if r["qc_phase1_score"] >= tau]
            n_by_tau[tau] = len(kept_qa)
            for c in conds:
                scores = [cond_scores_by[c][r["qa_id"]]
                          for r in kept_qa if r["qa_id"] in cond_scores_by[c]]
                means_by_tau[tau][c] = float(np.mean(scores)) if scores else float("nan")
        baseline_vec = [means_by_tau[baseline_tau][c] for c in conds]
        cat_out = {}
        for tau in taus:
            this_vec = [means_by_tau[tau][c] for c in conds]
            n_pairs = n_by_tau[tau]
            # Drop conditions with NaN at either point
            paired = [(b, t) for b, t in zip(baseline_vec, this_vec)
                      if not (np.isnan(b) or np.isnan(t))]
            if len(paired) < 3 or n_pairs == 0:
                cat_out[str(tau)] = {
                    "kendall_tau": float("nan"),
                    "p_value": float("nan"),
                    "n_pairs": n_pairs,
                    "n_conditions": len(paired),
                }
                continue
            b_vec, t_vec = zip(*paired)
            kt, p = kendalltau(b_vec, t_vec)
            cat_out[str(tau)] = {
                "kendall_tau": float(kt) if not np.isnan(kt) else float("nan"),
                "p_value": float(p) if not np.isnan(p) else float("nan"),
                "n_pairs": n_pairs,
                "n_conditions": len(paired),
            }
        out[qt] = cat_out
    return out


def format_pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def main():
    print("Loading QA scores...")
    qa_rows = load_qa_scores()
    tiers = load_network_tiers()
    for r in qa_rows:
        r["tier"] = tiers.get(r["network_id"], "unknown")
    print(f"  Loaded {len(qa_rows)} QA pairs across {len(set(r['network_id'] for r in qa_rows))} networks")

    # Distribution stats
    all_scores = np.array([r["qc_phase1_score"] for r in qa_rows])
    dist = {
        "n": int(all_scores.size),
        "mean": float(all_scores.mean()),
        "median": float(np.median(all_scores)),
        "std": float(all_scores.std()),
        "min": float(all_scores.min()),
        "p05": float(np.percentile(all_scores, 5)),
        "p10": float(np.percentile(all_scores, 10)),
        "p25": float(np.percentile(all_scores, 25)),
        "p75": float(np.percentile(all_scores, 75)),
        "p95": float(np.percentile(all_scores, 95)),
        "max": float(all_scores.max()),
        "frac_at_1p0": float((all_scores == 1.0).mean()),
        "frac_below_0p7": float((all_scores < 0.7).mean()),
        "frac_below_0p5": float((all_scores < 0.5).mean()),
    }

    # Per-network means
    net_means = per_network_mean(qa_rows)
    net_mean_vals = np.array(list(net_means.values()))
    net_dist = {
        "n_networks": int(net_mean_vals.size),
        "min": float(net_mean_vals.min()),
        "mean_of_means": float(net_mean_vals.mean()),
        "median": float(np.median(net_mean_vals)),
        "min_network": min(net_means, key=net_means.get),
    }

    # Coverage sweep
    print("Computing coverage sweep...")
    coverage = [coverage_at_tau(qa_rows, tau) for tau in TAUS]

    # Network mean-gate sweep
    dropout = [network_dropout(net_means, g) for g in MEAN_GATES]

    # Condition accuracy sweep
    print("Loading condition results...")
    cond_scores = {c: load_condition_scores(c) for c in CONDITIONS}
    for c in CONDITIONS:
        print(f"  {c}: {len(cond_scores[c])} QA scores loaded")

    print("Computing per-condition accuracy at each tau...")
    cond_at_tau = {c: {} for c in CONDITIONS}
    cond_means_by_tau = {tau: {} for tau in TAUS}
    for tau in TAUS:
        for c in CONDITIONS:
            res = condition_accuracy_at_tau(qa_rows, cond_scores[c], tau)
            cond_at_tau[c][str(tau)] = res
            cond_means_by_tau[tau][c] = res["mean"]

    # Rank stability (overall)
    print("Computing rank stability (Kendall tau)...")
    stability = rank_stability(cond_means_by_tau, baseline_tau=0.00)

    # Per-category rank stability
    print("Computing per-category rank stability...")
    per_cat_stability = per_category_rank_stability(
        qa_rows, cond_scores, TAUS, baseline_tau=0.00
    )

    # Best - worst gap at each tau (headline invariance)
    gap_at_tau = {}
    for tau in TAUS:
        means = [m for m in cond_means_by_tau[tau].values() if not np.isnan(m)]
        if means:
            gap_at_tau[str(tau)] = {
                "best": float(max(means)),
                "worst": float(min(means)),
                "gap": float(max(means) - min(means)),
            }

    out = {
        "qc_distribution": dist,
        "network_mean_distribution": net_dist,
        "coverage_sweep": coverage,
        "network_dropout_by_mean_gate": dropout,
        "condition_accuracy_by_tau": cond_at_tau,
        "rank_stability_vs_baseline_tau_0.00": stability,
        "per_category_rank_stability_vs_baseline_tau_0.00": per_cat_stability,
        "headline_gap_at_tau": gap_at_tau,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {OUT_PATH}")

    # Printable summary
    print("\n" + "=" * 72)
    print("PER-QA BLIND-CRITIC SCORE DISTRIBUTION")
    print("=" * 72)
    print(f"N = {dist['n']:,} QA pairs, {net_dist['n_networks']} networks")
    print(f"Mean {dist['mean']:.3f} | Median {dist['median']:.3f} | Std {dist['std']:.3f}")
    print(f"Min {dist['min']:.2f} | p05 {dist['p05']:.2f} | p25 {dist['p25']:.2f} | p75 {dist['p75']:.2f}")
    print(f"Fraction == 1.0: {format_pct(dist['frac_at_1p0'])}")
    print(f"Fraction < 0.7:  {format_pct(dist['frac_below_0p7'])}")
    print(f"Fraction < 0.5:  {format_pct(dist['frac_below_0p5'])}")
    print(f"Per-network mean floor: {net_dist['min']:.3f} ({net_dist['min_network']})")

    print("\n" + "=" * 72)
    print("COVERAGE RETENTION @ PER-QA THRESHOLD tau")
    print("=" * 72)
    print(f"{'tau':>6} {'kept':>6} {'total':>6} {'retention':>10}")
    for c in coverage:
        print(f"{c['tau']:>6.2f} {c['kept']:>6} {c['total']:>6} {format_pct(c['retention']):>10}")

    print("\n" + "=" * 72)
    print("NETWORK DROPOUT @ PER-NETWORK MEAN GATE")
    print("=" * 72)
    print(f"{'gate':>6} {'kept':>6} {'dropped':>8}")
    for d in dropout:
        print(f"{d['gate']:>6.2f} {d['kept_count']:>6} {d['dropped_count']:>8}")

    print("\n" + "=" * 72)
    print("PER-CONDITION MEAN ACCURACY @ EACH tau")
    print("=" * 72)
    hdr = f"{'condition':<14}" + "".join(f"{tau:>7.2f}" for tau in TAUS)
    print(hdr)
    for c in CONDITIONS:
        row = f"{c:<14}"
        for tau in TAUS:
            m = cond_at_tau[c][str(tau)]["mean"]
            row += f"{m:>7.3f}" if not np.isnan(m) else f"{'nan':>7}"
        print(row)

    print("\n" + "=" * 72)
    print("RANK STABILITY: Kendall tau vs. baseline (tau=0.00, all QA)")
    print("=" * 72)
    print(f"{'tau':>6} {'kendall':>10} {'p':>10}")
    for tau in TAUS:
        s = stability[str(tau)]
        k = s["kendall_tau"]
        p = s["p_value"]
        k_str = f"{k:.3f}" if not np.isnan(k) else "nan"
        p_str = f"{p:.4f}" if not np.isnan(p) else "nan"
        print(f"{tau:>6.2f} {k_str:>10} {p_str:>10}")

    print("\n" + "=" * 72)
    print("HEADLINE GAP (best - worst condition) @ EACH tau")
    print("=" * 72)
    print(f"{'tau':>6} {'best':>7} {'worst':>7} {'gap':>7}")
    for tau in TAUS:
        g = gap_at_tau.get(str(tau))
        if g:
            print(f"{tau:>6.2f} {g['best']:>7.3f} {g['worst']:>7.3f} {g['gap']:>7.3f}")

    print("\n" + "=" * 72)
    print("PER-CATEGORY RANK STABILITY: Kendall tau vs. baseline (tau=0.00)")
    print("=" * 72)
    qtypes = sorted(per_cat_stability.keys())
    hdr = f"{'qt':<4}" + "".join(f"{tau:>8.2f}" for tau in TAUS)
    print(hdr)
    for qt in qtypes:
        row = f"{qt:<4}"
        for tau in TAUS:
            entry = per_cat_stability[qt][str(tau)]
            k = entry["kendall_tau"]
            row += f"{k:>8.3f}" if not np.isnan(k) else f"{'nan':>8}"
        print(row)
    # Also print n_pairs per (qt, tau) to sanity-check where NaN comes from
    print("\nSample sizes (n_pairs) per (query_type, tau):")
    print(hdr)
    for qt in qtypes:
        row = f"{qt:<4}"
        for tau in TAUS:
            n = per_cat_stability[qt][str(tau)]["n_pairs"]
            row += f"{n:>8d}"
        print(row)


if __name__ == "__main__":
    main()
