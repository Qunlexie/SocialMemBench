"""
fix_pci_verbatim.py — ensure every `planted_challenge_index[].evidence_span`
is a verbatim substring of the conversation turn at its `(session_index,
turn_index)` location.

Three repair modes are tried in order per entry:

  1. **Off-by-one bump**: if the span appears at `turn_index + 1` (a common
     1-vs-0-indexing artifact from older generators), bump turn_index.
  2. **Replace with verbatim turn**: if the listed turn doesn't contain the
     span and no nearby bump works, the span is paraphrastic — replace the
     `evidence_span` with the actual message text at the listed turn.
  3. **Fuzzy retarget**: if turn_index is 0/out-of-range OR no nearby turn
     matches, search the whole corpus for the longest contiguous
     word-substring of the span and retarget (session_index, turn_index) to
     that turn, replacing evidence_span with the verbatim message.

Use after generation, after option-C backfill, or whenever PCI gets out of sync.

Usage:
    python scripts/fix_pci_verbatim.py             # apply across all networks
    python scripts/fix_pci_verbatim.py --dry-run   # report-only
    python scripts/fix_pci_verbatim.py --network grp_xxxxxxxx
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONV_DIR = REPO_ROOT / "data" / "conversations"


def get_turn(conv: dict, si: int | None, ti: int | None) -> dict | None:
    if si is None or ti is None: return None
    if si < 1 or si > len(conv["sessions"]): return None
    sess = conv["sessions"][si - 1]
    turns = sess.get("turns", []) or []
    if ti < 1 or ti > len(turns): return None
    return turns[ti - 1]


def fuzzy_match(conv: dict, span: str, min_seed_chars: int = 15):
    """Find corpus turn whose message contains the longest contiguous phrase from `span`."""
    words = span.split()
    candidates: list[str] = []
    for L in range(min(len(words), 12), 3, -1):
        for start in range(len(words) - L + 1):
            phrase = " ".join(words[start:start + L])
            if len(phrase) >= min_seed_chars:
                candidates.append(phrase)
    for phrase in sorted(set(candidates), key=lambda p: -len(p)):
        for si, sess in enumerate(conv["sessions"], 1):
            for ti, t in enumerate(sess.get("turns", []) or [], 1):
                if phrase in t.get("message", ""):
                    return si, ti, t["message"]
    return None


def fix_pci(conv: dict) -> tuple[int, int, int, int]:
    """Returns (n_already_ok, n_bumped, n_replaced, n_fuzzy_retargeted)."""
    pci = conv.get("planted_challenge_index", []) or []
    n_ok = n_bumped = n_replaced = n_fuzzy = 0
    for c in pci:
        si, ti = c.get("session_index"), c.get("turn_index")
        span = c.get("evidence_span", "")

        # Already verbatim?
        cur = get_turn(conv, si, ti)
        if cur and span in cur.get("message", ""):
            n_ok += 1
            continue

        # Mode 1: +1 bump
        nxt = get_turn(conv, si, (ti or 0) + 1) if si else None
        if nxt and span in nxt.get("message", ""):
            c["turn_index"] = ti + 1
            n_bumped += 1
            continue

        # Mode 2: replace span with verbatim listed-turn message
        if cur:
            c["evidence_span"] = cur["message"]
            n_replaced += 1
            continue

        # Mode 3: fuzzy retarget (also covers turn_index=0 / out-of-range)
        result = fuzzy_match(conv, span)
        if result:
            new_si, new_ti, new_msg = result
            c["session_index"] = new_si
            c["turn_index"] = new_ti
            c["evidence_span"] = new_msg
            n_fuzzy += 1
            continue

        # Truly unfixable
    return n_ok, n_bumped, n_replaced, n_fuzzy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--network", help="Process a single network ID (default: all)")
    args = ap.parse_args()

    if args.network:
        targets = [CONV_DIR / f"{args.network}.json"]
    else:
        targets = sorted(CONV_DIR.glob("grp_*.json"))

    totals = {"ok": 0, "bumped": 0, "replaced": 0, "fuzzy": 0, "files_changed": 0}
    for path in targets:
        if not path.exists():
            print(f"  skip {path.name}: not found")
            continue
        conv = json.load(open(path))
        snapshot = json.dumps(conv, sort_keys=True)
        n_ok, n_bumped, n_replaced, n_fuzzy = fix_pci(conv)
        new_snapshot = json.dumps(conv, sort_keys=True)
        totals["ok"] += n_ok; totals["bumped"] += n_bumped
        totals["replaced"] += n_replaced; totals["fuzzy"] += n_fuzzy
        if snapshot != new_snapshot:
            totals["files_changed"] += 1
            if not args.dry_run:
                path.write_text(json.dumps(conv, indent=2))
        if n_bumped or n_replaced or n_fuzzy:
            print(f"  {path.stem}: ok={n_ok} bump={n_bumped} replace={n_replaced} fuzzy={n_fuzzy}")

    print(f"\nTotals: already_ok={totals['ok']} bump={totals['bumped']} "
          f"replace={totals['replaced']} fuzzy={totals['fuzzy']} files_changed={totals['files_changed']}"
          f"{' (dry-run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
