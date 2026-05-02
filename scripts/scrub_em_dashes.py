"""
scrub_em_dashes.py — replace em-dashes (`—` U+2014) with ` - ` in all
conversation message fields, AND update any planted_challenge_index
evidence_span / qa.evidence_anchors[].message_excerpt that referenced those
turns so they remain verbatim substrings of the new message text.

The verify rule says zero em-dashes in `message` fields. Earlier ad-hoc fixes
preserved em-dashes in turns referenced by anchors (to keep verbatim) — that
left a real conflict between two checks. This script resolves it correctly:
the message and the anchor are updated in lockstep so both checks pass.

Usage:
    python scripts/scrub_em_dashes.py
    python scripts/scrub_em_dashes.py --dry-run
    python scripts/scrub_em_dashes.py --network grp_xxxxxxxx
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONV_DIR = REPO_ROOT / "data" / "conversations"
QA_DIR = REPO_ROOT / "data" / "qa"

EM_DASH = "—"
REPLACEMENT = " - "


def normalize(s: str) -> str:
    """Apply em-dash replacement and collapse double spaces."""
    out = s.replace(EM_DASH, REPLACEMENT)
    while "  " in out:
        out = out.replace("  ", " ")
    return out


def fix_network(nid: str, dry_run: bool = False) -> dict:
    cp = CONV_DIR / f"{nid}.json"
    qp = QA_DIR / f"{nid}.jsonl"
    if not cp.exists():
        return {"err": f"missing {cp}"}
    conv = json.load(open(cp))
    turns_changed: dict[str, tuple[str, str]] = {}

    for s in conv.get("sessions", []) or []:
        for t in s.get("turns", []) or []:
            msg = t.get("message", "")
            if EM_DASH in msg:
                old = msg
                new = normalize(msg)
                turns_changed[t.get("turn_id")] = (old, new)
                if not dry_run:
                    t["message"] = new

    n_pci_fixed = 0
    for c in conv.get("planted_challenge_index", []) or []:
        si, ti = c.get("session_index"), c.get("turn_index")
        if not si or not ti or si < 1 or si > len(conv["sessions"]):
            continue
        sess = conv["sessions"][si - 1]
        if ti < 1 or ti > len(sess.get("turns", []) or []):
            continue
        turn = sess["turns"][ti - 1]
        tid = turn.get("turn_id")
        if tid in turns_changed and EM_DASH in c.get("evidence_span", ""):
            new_msg = turns_changed[tid][1]
            test = normalize(c["evidence_span"])
            if not dry_run:
                c["evidence_span"] = test if test in new_msg else new_msg
            n_pci_fixed += 1

    if not dry_run:
        cp.write_text(json.dumps(conv, indent=2))

    n_anchor_fixed = 0
    if qp.exists() and turns_changed:
        rows = [json.loads(line) for line in open(qp) if line.strip()]
        changed = False
        for d in rows:
            for a in d.get("evidence_anchors", []) or []:
                tid = a.get("turn_id")
                if tid in turns_changed and EM_DASH in a.get("message_excerpt", ""):
                    new_msg = turns_changed[tid][1]
                    test = normalize(a["message_excerpt"])
                    if not dry_run:
                        a["message_excerpt"] = test if test in new_msg else new_msg
                    n_anchor_fixed += 1
                    changed = True
        if changed and not dry_run:
            qp.write_text("\n".join(json.dumps(d) for d in rows) + "\n")

    return {"messages_fixed": len(turns_changed),
            "pci_anchors_realigned": n_pci_fixed,
            "qa_anchors_realigned": n_anchor_fixed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--network", help="Process a single network ID (default: all)")
    args = ap.parse_args()

    targets = ([args.network] if args.network
               else sorted(p.stem for p in CONV_DIR.glob("grp_*.json")))

    totals = {"messages_fixed": 0, "pci_anchors_realigned": 0, "qa_anchors_realigned": 0}
    for nid in targets:
        result = fix_network(nid, dry_run=args.dry_run)
        if "err" in result:
            print(f"  {nid}: {result['err']}")
            continue
        if result["messages_fixed"]:
            print(f"  {nid}: msgs={result['messages_fixed']} "
                  f"pci={result['pci_anchors_realigned']} "
                  f"qa={result['qa_anchors_realigned']}")
        for k in totals:
            totals[k] += result[k]
    mode = " (dry-run)" if args.dry_run else ""
    print(f"\nTotals: {totals}{mode}")


if __name__ == "__main__":
    main()
