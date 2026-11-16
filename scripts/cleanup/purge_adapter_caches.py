"""
List adapter caches under data/ (Chroma vector stores, Kuzu graph DBs,
langmem/cognee scratch) and, with --purge, remove them.

All matched directories are already gitignored (see .gitignore). They are
regeneratable via each adapter's ingest step at API cost. Removing them frees
substantial disk space (Graphiti alone is ~1.7 GB in this repo).

Defaults to dry-run: prints what would be freed but changes nothing. Pass
--purge to actually remove.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

# Directories to consider. All are gitignored. Add here if new adapters land.
CACHE_DIRS = [
    ".graphiti_db",
    ".graphiti_db_ext=gpt-4o",
    ".graphiti",
    ".naive_rag_chroma",
    ".subject_rag_chroma",
    ".attributed_rag_chroma",
    ".hybrid_rag_chroma",
    ".norm_aware_rag_chroma",
    ".mem0_chroma",
    ".mem0",
    ".cognee_db",
    ".cognee",
    ".langmem",
    ".smg_graphs",
    ".smg_graphs_gemini",
]


def dir_size(path: Path) -> int:
    try:
        out = subprocess.check_output(
            ["du", "-sk", str(path)], stderr=subprocess.DEVNULL
        ).decode()
        return int(out.split()[0]) * 1024
    except Exception:
        return 0


def humansize(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--purge", action="store_true",
                    help="Actually remove the directories (default: dry-run).")
    ap.add_argument("--only", nargs="*", default=None,
                    help="Restrict to a subset of cache names (e.g. --only .graphiti_db)")
    args = ap.parse_args()

    if not DATA.exists():
        print(f"No data/ dir at {DATA}")
        return 0

    total = 0
    hits = []
    for name in CACHE_DIRS:
        if args.only and name not in args.only:
            continue
        p = DATA / name
        if not p.exists():
            continue
        sz = dir_size(p)
        total += sz
        hits.append((p, sz))

    if not hits:
        print("No adapter caches present.")
        return 0

    print(f"{'SIZE':>10}  PATH")
    for p, sz in sorted(hits, key=lambda x: -x[1]):
        print(f"{humansize(sz):>10}  {p.relative_to(ROOT)}")
    print("-" * 60)
    print(f"Total: {len(hits)} caches, {humansize(total)}")

    if not args.purge:
        print("\nDry-run (default). Re-run with --purge to remove.")
        return 0

    print("\nPurging ...")
    for p, _ in hits:
        try:
            shutil.rmtree(p)
            print(f"  removed {p.relative_to(ROOT)}")
        except Exception as e:
            print(f"  FAILED to remove {p.relative_to(ROOT)}: {e}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
