"""
backfill_active_participants.py — fill `session.active_participants` for any
session where it's missing or empty, by taking the union of `speaker_persona_id`
values from that session's turns. Honest derivation: who actually spoke in the
session IS who was active.

Use after generating new conversations; run idempotently as part of the
data-cleanup loop.

Usage:
    python scripts/backfill_active_participants.py
    python scripts/backfill_active_participants.py --dry-run
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONV_DIR = REPO_ROOT / "data" / "conversations"


def derive_active_participants(session: dict) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in session.get("turns", []) or []:
        spk = t.get("speaker_persona_id")
        if spk and spk not in seen:
            seen.add(spk)
            out.append(spk)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    n_filled = 0
    n_skipped = 0
    for path in sorted(CONV_DIR.glob("grp_*.json")):
        conv = json.load(open(path))
        local = 0
        for s in conv.get("sessions", []):
            if s.get("active_participants"):
                n_skipped += 1
                continue
            participants = derive_active_participants(s)
            if not participants:
                continue
            if not args.dry_run:
                s["active_participants"] = participants
            local += 1
        if local and not args.dry_run:
            path.write_text(json.dumps(conv, indent=2))
        n_filled += local
        if local:
            print(f"  {path.stem}: filled {local} sessions")

    mode = "would fill" if args.dry_run else "filled"
    print(f"\nTotal: {mode} {n_filled} sessions ({n_skipped} already had data)")


if __name__ == "__main__":
    main()
