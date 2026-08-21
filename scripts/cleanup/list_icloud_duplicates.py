"""
List (do not remove) iCloud sync duplicate directories.

iCloud produces shadow copies of directories under the naming pattern
`<name> 2/`, `<name> 3/`, etc. In this repo they show up under
`data/results/`, `data/results_archive_prerun_*/`, `eval/config/adapters/`,
and `.claude/commands/`. They are byte-identical to their originals and are
already gitignored (via the `* [0-9]` rule in `.gitignore`).

This script:
  1. Enumerates every such duplicate under the repo root.
  2. Confirms the corresponding original exists.
  3. Prints total size that would be freed by removal.
  4. Emits a shell command you can run manually to remove them.

It does NOT remove anything. Deletion is left to the operator.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Suffix pattern: exactly a space and one or two digits at the end.
DUP_RE = re.compile(r" (\d{1,2})$")


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


def find_dupes(root: Path):
    dupes = []
    for dirpath, dirnames, _ in os.walk(root):
        # Skip .git and node_modules for speed.
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "__pycache__"}]
        for d in dirnames:
            m = DUP_RE.search(d)
            if not m:
                continue
            dup_path = Path(dirpath) / d
            original_name = DUP_RE.sub("", d)
            orig_path = Path(dirpath) / original_name
            dupes.append((dup_path, orig_path, orig_path.exists()))
    return sorted(dupes)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root", default=str(ROOT), help="Repo root (default: two parents up)"
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    dupes = find_dupes(root)

    if not dupes:
        print("No iCloud sync duplicates found.")
        return 0

    total = 0
    print(f"{'ORIG?':<7} {'SIZE':>10}  DUPLICATE")
    print("-" * 80)
    to_remove = []
    for dup, orig, orig_exists in dupes:
        size = dir_size(dup)
        total += size
        marker = "yes" if orig_exists else "MISS"
        print(f"{marker:<7} {humansize(size):>10}  {dup.relative_to(root)}")
        if orig_exists:
            to_remove.append(dup)

    print("-" * 80)
    print(f"Total: {len(dupes)} duplicates, {humansize(total)}")
    if any(not orig for _, _, orig in dupes):
        print("WARNING: duplicates marked MISS have no matching original; verify before removing.")

    if to_remove:
        print("\nTo remove (only after reviewing above), run:")
        print()
        for p in to_remove:
            rel = p.relative_to(root)
            print(f'  rm -rf "{rel}"')
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
