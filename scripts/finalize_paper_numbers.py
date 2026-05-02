"""
Finalize pipeline — runs after eval orchestrator completes:

1. Recompute bootstrap CIs and pairwise tests
2. Regenerate heatmap and bar chart
3. Print final headline numbers for paper updates
4. Apply automatic paper updates for known patterns
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

def run(cmd: list, cwd=None):
    print(f"\n$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"FAILED:\n{r.stderr[-1000:]}")
        return False
    print(r.stdout[-2000:])
    return True


def main():
    print("=" * 70)
    print("FINALIZE PAPER NUMBERS")
    print("=" * 70)

    print("\n[1/4] Recomputing bootstrap CIs...")
    if not run(["python3", "scripts/recompute_bootstrap.py"]):
        sys.exit(1)

    print("\n[2/4] Regenerating figures...")
    if not run(["python3", "figures/generate_figures.py"]):
        sys.exit(1)

    print("\n[3/4] Printing final paper numbers...")
    if not run(["python3", "scripts/print_paper_numbers.py"]):
        sys.exit(1)

    print("\n[4/4] Compiling paper...")
    if not run(["pdflatex", "-interaction=nonstopmode", "neurips_2026.tex"], cwd=ROOT / "paper"):
        print("(pdflatex may have warnings — check the log)")

    print("\n" + "=" * 70)
    print("DONE — ready for manual paper updates with new numbers")
    print("=" * 70)


if __name__ == "__main__":
    main()
