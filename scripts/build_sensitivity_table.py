"""
Emit paper-ready summary table for the QC threshold sensitivity analysis.

Reads data/verify/sensitivity_qc_threshold.json and writes:
  - data/verify/sensitivity_threshold_table.tex  (LaTeX, booktabs style)
  - data/verify/sensitivity_threshold_table.csv  (CSV mirror)

Does not touch anything under paper/.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
IN_PATH = ROOT / "data" / "verify" / "sensitivity_qc_threshold.json"
OUT_TEX = ROOT / "data" / "verify" / "sensitivity_threshold_table.tex"
OUT_CSV = ROOT / "data" / "verify" / "sensitivity_threshold_table.csv"

# Thresholds to include in the paper-facing table.
# Chose the operating range: 0.70 (rubric gate) up to 0.95 (well past mean).
TAUS = [0.70, 0.80, 0.85, 0.90, 0.95]


def load():
    return json.load(open(IN_PATH))


def rows_for(data: dict):
    cov = {c["tau"]: c for c in data["coverage_sweep"]}
    stab = data["rank_stability_vs_baseline_tau_0.00"]
    gap = data["headline_gap_at_tau"]
    rows = []
    for tau in TAUS:
        c = cov[tau]
        s = stab[str(tau)]
        g = gap[str(tau)]
        rows.append({
            "tau": tau,
            "kept": c["kept"],
            "total": c["total"],
            "retention_pct": 100.0 * c["retention"],
            "kendall_tau": s["kendall_tau"],
            "best": g["best"],
            "worst": g["worst"],
            "gap": g["gap"],
        })
    return rows


def write_tex(rows):
    header = (
        r"\begin{table}[t!]" + "\n"
        r"  \caption{Sensitivity of dataset composition and downstream evaluation "
        r"to the per-QA blind-critic threshold $\tau$. Retention is the fraction "
        r"of the $N{=}1{,}031$ QA pairs whose $\text{qc\_phase1\_score} \geq \tau$. "
        r"Kendall $\tau$ compares the ranking of the eight evaluated conditions at "
        r"threshold $\tau$ against the ranking with no filtering. "
        r"Best$-$worst gap is the accuracy spread between the top and bottom "
        r"condition on the retained subset.}" + "\n"
        r"  \label{tab:sensitivity-threshold}" + "\n"
        r"  \centering" + "\n"
        r"  \small" + "\n"
        r"  \begin{tabular}{lcccc}" + "\n"
        r"    \toprule" + "\n"
        r"    \textbf{$\tau$} & \textbf{Retention} & "
        r"\textbf{Kendall $\tau$ vs.\ no gate} & "
        r"\textbf{Best$-$worst gap} \\" + "\n"
        r"    \midrule" + "\n"
    )
    body_lines = []
    for r in rows:
        body_lines.append(
            f"    {r['tau']:.2f} & "
            f"{r['retention_pct']:.1f}\\% & "
            f"{r['kendall_tau']:.3f} & "
            f"{r['gap']:.3f} \\\\"
        )
    footer = (
        r"    \bottomrule" + "\n"
        r"  \end{tabular}" + "\n"
        r"\end{table}" + "\n"
    )
    OUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_TEX, "w") as f:
        f.write(header + "\n".join(body_lines) + "\n" + footer)


def write_csv(rows):
    fields = ["tau", "kept", "total", "retention_pct",
              "kendall_tau", "best", "worst", "gap"]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    data = load()
    rows = rows_for(data)
    write_tex(rows)
    write_csv(rows)
    print(f"Wrote {OUT_TEX}")
    print(f"Wrote {OUT_CSV}")
    print()
    print("Preview:")
    print(f"{'tau':>5} {'retention':>10} {'kendall':>9} {'gap':>7}")
    for r in rows:
        print(f"{r['tau']:>5.2f} {r['retention_pct']:>9.1f}% "
              f"{r['kendall_tau']:>9.3f} {r['gap']:>7.3f}")


if __name__ == "__main__":
    main()
