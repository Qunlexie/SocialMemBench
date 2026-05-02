"""
Dedup result JSONL files: keep only the LAST occurrence of each qa_id, and only
keep qa_ids that exist in the current QA file (drop orphans from cut/rewritten
pairs). Backs up before modifying.

Why this matters: when the QA generation rewrite produced new question text for
some qa_ids and the eval CLI was re-run, the new evaluations were appended to
the existing JSONL files without removing old rows. The aggregation scripts
read every row, so duplicates were inflating sample sizes and (where scores
differed across runs) skewing means.

The post-rewrite (last-appended) row is the canonical one because it reflects
the current question text.
"""
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "data" / "results"
QA_DIR = ROOT / "data" / "qa"
BACKUP_DIR = ROOT / "data" / "results.backup_pre_dedup"


def load_valid_qa_ids(network_id: str) -> set[str]:
    qa_path = QA_DIR / f"{network_id}.jsonl"
    if not qa_path.exists():
        return set()
    ids = set()
    for line in open(qa_path):
        if line.strip():
            d = json.loads(line)
            qid = d.get("qa_id")
            if qid:
                ids.add(qid)
    return ids


def dedup_file(path: Path, valid_qa_ids: set[str]) -> tuple[int, int, int]:
    """Returns (original_rows, kept_rows, dropped_orphans)."""
    rows = []
    for line in open(path):
        if not line.strip():
            continue
        rows.append(json.loads(line))

    # Last occurrence wins per qa_id
    by_id = {}
    for d in rows:
        qid = d.get("qa_id")
        if qid:
            by_id[qid] = d

    # Filter to valid qa_ids only (drop orphans from rewrites that changed qa_ids)
    orphans = sum(1 for qid in by_id if qid not in valid_qa_ids) if valid_qa_ids else 0
    if valid_qa_ids:
        by_id = {qid: d for qid, d in by_id.items() if qid in valid_qa_ids}

    return len(rows), len(by_id), orphans, by_id


def main():
    dry_run = "--apply" not in sys.argv
    print(f"Mode: {'DRY RUN (use --apply to write)' if dry_run else 'APPLY'}")

    if not dry_run:
        if BACKUP_DIR.exists():
            print(f"Backup already exists at {BACKUP_DIR}; aborting to avoid overwriting.")
            sys.exit(1)
        shutil.copytree(RESULTS_DIR, BACKUP_DIR)
        print(f"Backup saved: {BACKUP_DIR}")

    total_files = 0
    total_orig = 0
    total_kept = 0
    total_orphans = 0
    affected = []

    for cond_dir in sorted(RESULTS_DIR.iterdir()):
        if not cond_dir.is_dir():
            continue
        for jsonl in sorted(cond_dir.glob("*.jsonl")):
            nid = jsonl.stem
            valid = load_valid_qa_ids(nid)
            if not valid:
                continue
            orig_n, kept_n, orphans, by_id = dedup_file(jsonl, valid)
            total_files += 1
            total_orig += orig_n
            total_kept += kept_n
            total_orphans += orphans

            if orig_n != kept_n:
                affected.append((str(jsonl.relative_to(ROOT)), orig_n, kept_n, orphans))
                if not dry_run:
                    with open(jsonl, "w") as f:
                        for d in by_id.values():
                            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"\n=== SUMMARY ===")
    print(f"Files scanned: {total_files}")
    print(f"Total rows before: {total_orig}")
    print(f"Total rows after:  {total_kept}")
    print(f"Total orphan rows dropped: {total_orphans}")
    print(f"Files affected: {len(affected)}")

    if affected:
        print(f"\nTop 15 affected files (by rows-removed):")
        affected.sort(key=lambda x: x[1] - x[2], reverse=True)
        for path, before, after, orph in affected[:15]:
            print(f"  {before:>4} -> {after:<4}  ({before-after:>3} dropped, {orph} orphans)  {path}")


if __name__ == "__main__":
    main()
