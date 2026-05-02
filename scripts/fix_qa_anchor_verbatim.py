"""
fix_qa_anchor_verbatim.py — ensure every `qa.evidence_anchors[].message_excerpt`
is a verbatim substring of the conversation turn it claims to anchor to.

Two repair modes are tried in order per anchor:

  1. **Restore from same turn**: if the listed turn (looked up by `turn_id` or
     `(session_index, turn_index)`) contains the longest leading prefix of the
     excerpt, replace the excerpt with the verbatim slice from the corpus that
     starts at the same point. Fixes emoji-loss and trailing-punctuation drift
     without changing what the anchor refers to.
  2. **Re-anchor**: if the listed turn doesn't contain the excerpt's leading
     content at all, search the corpus for the first turn that does and
     retarget `turn_id` / `session_index` / `turn_index`.

Use after generation, after rewrite passes, or whenever QA anchors drift from
their referenced corpus content.

Usage:
    python scripts/fix_qa_anchor_verbatim.py
    python scripts/fix_qa_anchor_verbatim.py --dry-run
    python scripts/fix_qa_anchor_verbatim.py --network grp_xxxxxxxx
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
QA_DIR = REPO_ROOT / "data" / "qa"
CONV_DIR = REPO_ROOT / "data" / "conversations"


def msg_by_turn_id(conv: dict, turn_id: str) -> str | None:
    for sess in conv.get("sessions", []) or []:
        for t in sess.get("turns", []) or []:
            if t.get("turn_id") == turn_id:
                return t.get("message")
    return None


def msg_at(conv: dict, si: int | None, ti: int | None) -> str | None:
    if si is None or ti is None: return None
    if si < 1 or si > len(conv["sessions"]): return None
    sess = conv["sessions"][si - 1]
    turns = sess.get("turns", []) or []
    if ti < 1 or ti > len(turns): return None
    return turns[ti - 1].get("message")


def best_seed(corpus_msg: str, broken: str, min_len: int = 10) -> str:
    """Longest leading prefix of `broken` that's a substring of `corpus_msg`."""
    for L in range(min(len(broken), 200), min_len, -1):
        seed = broken[:L]
        if seed in corpus_msg:
            return seed
    return ""


def restore_from_turn(corpus_msg: str, broken: str) -> str | None:
    """Mode 1: take a verbatim slice of corpus_msg starting at the longest seed match."""
    seed = best_seed(corpus_msg, broken)
    if not seed: return None
    idx = corpus_msg.index(seed)
    target_len = min(len(broken) + 6, len(corpus_msg) - idx)
    return corpus_msg[idx:idx + target_len].rstrip()


def find_turn_containing(conv: dict, text: str):
    for si, sess in enumerate(conv.get("sessions", []) or [], 1):
        for ti, t in enumerate(sess.get("turns", []) or [], 1):
            if text in t.get("message", ""):
                return si, ti, t.get("turn_id"), t.get("message")
    return None


def fix_anchors_in_pair(qa: dict, conv: dict) -> dict:
    counts = {"ok": 0, "mode1": 0, "mode2": 0, "unfixable": 0}
    for a in qa.get("evidence_anchors", []) or []:
        ex = a.get("message_excerpt", "")
        if not ex: continue
        tid = a.get("turn_id")
        msg = msg_by_turn_id(conv, tid) if tid else msg_at(conv, a.get("session_index"), a.get("turn_index"))

        if msg and ex in msg:
            counts["ok"] += 1
            continue

        # Mode 1
        if msg:
            restored = restore_from_turn(msg, ex)
            if restored:
                a["message_excerpt"] = restored
                counts["mode1"] += 1
                continue

        # Mode 2
        seed_for_search = ex[:25].rstrip()
        if seed_for_search:
            result = find_turn_containing(conv, seed_for_search)
            if result:
                si2, ti2, new_tid, new_msg = result
                a["turn_id"] = new_tid
                a["session_index"] = si2
                a["turn_index"] = ti2
                a["message_excerpt"] = restore_from_turn(new_msg, ex) or new_msg
                counts["mode2"] += 1
                continue

        counts["unfixable"] += 1
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--network", help="Process a single network ID (default: all)")
    args = ap.parse_args()

    qa_paths = ([QA_DIR / f"{args.network}.jsonl"] if args.network
                else sorted(QA_DIR.glob("grp_*.jsonl")))

    totals = {"ok": 0, "mode1": 0, "mode2": 0, "unfixable": 0, "files_changed": 0}
    for qa_path in qa_paths:
        if not qa_path.exists(): continue
        conv_path = CONV_DIR / f"{qa_path.stem}.json"
        if not conv_path.exists():
            print(f"  skip {qa_path.stem}: missing conversations file")
            continue
        conv = json.load(open(conv_path))
        rows = [json.loads(line) for line in open(qa_path) if line.strip()]
        before = json.dumps(rows, sort_keys=True)
        local = {"ok": 0, "mode1": 0, "mode2": 0, "unfixable": 0}
        for d in rows:
            c = fix_anchors_in_pair(d, conv)
            for k in local: local[k] += c.get(k, 0)
        after = json.dumps(rows, sort_keys=True)
        for k in totals: totals[k] += local.get(k, 0) if k != "files_changed" else 0
        if before != after:
            totals["files_changed"] += 1
            if not args.dry_run:
                qa_path.write_text("\n".join(json.dumps(d) for d in rows) + "\n")
        if local["mode1"] or local["mode2"] or local["unfixable"]:
            print(f"  {qa_path.stem}: ok={local['ok']} mode1={local['mode1']} mode2={local['mode2']} unfixable={local['unfixable']}")

    print(f"\nTotals: ok={totals['ok']} mode1={totals['mode1']} mode2={totals['mode2']} "
          f"unfixable={totals['unfixable']} files_changed={totals['files_changed']}"
          f"{' (dry-run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
