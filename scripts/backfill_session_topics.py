"""
backfill_session_topics.py — backfill `topic` field for sessions in older-format
networks where it was missing.

Generation skill `smb-generate-conversations` now requires `topic` per session,
but networks generated before that requirement landed lack the field. This
script backfills with hand-curated topics inferred from actual session content.

Pattern for future use: if you find more topic-less sessions, add a topics dict
below for the network, and re-run.

Usage:
    python scripts/backfill_session_topics.py
    python scripts/backfill_session_topics.py --dry-run
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONV_DIR = REPO_ROOT / "data" / "conversations"

# Topic strings curated by inspecting session content. Topics describe the
# primary thread of each session, not the planted-challenge metadata.
TOPICS: dict[str, dict[int, str]] = {
    "grp_b2c3d4e5": {
        1: "Return-to-running planning: River Loop",
        2: "River Loop debrief and Ridgeline trail proposal",
        3: "Nadia's hamstring injury and Lakeview route options",
        4: "City 10K race entry discussion",
        5: "Pre-race Sunday run options",
        6: "Race week preparation",
        7: "Race-week taper",
        8: "Race day recap",
    },
    "grp_c3d4e5f6": {
        1: "New keycard entry system rollout",
        2: "Lobby package theft incident",
        3: "Building lockout and faulty keycard batch",
        4: "Lobby decoration ideas and Valentines plans",
        5: "Casual lobby chat and apartment memes",
        6: "Lobby coffee machine proposal",
        7: "Courtyard event scheduling for Feb 15-16",
        8: "Building BBQ recap",
    },
    "grp_e5f6a7b8": {
        1: "New Year check-in across the friend group",
        2: "Lake District April long-weekend planning",
        3: "Airbnb cottage selection near Grasmere",
        4: "Life updates and big news round",
        5: "Bex's Copenhagen move and group reactions",
        6: "Cottage booking confirmation",
        7: "Trip cost finalization and split",
        8: "Pre-trip logistics check-in",
        9: "Trip countdown (9 days)",
        10: "Post-trip recap and reflection",
    },
    "grp_f6g7h8i9": {
        1: "New Year greetings and family check-in",
        2: "Anniversary trip destination debate (Paris vs Lisbon vs Scotland)",
        3: "Scotland trip date confirmation",
        4: "Family check-in mid-planning",
        5: "Scotland activities and itinerary planning",
        6: "Budget update and per-adult cost discussion",
        7: "Minibus and transport arrangements",
        8: "Final headcount confirmation",
        9: "Trip countdown (9 days)",
        10: "Post-trip reflection and best-weekend recap",
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Report changes only")
    args = ap.parse_args()

    n_added = 0
    for nid, topic_map in TOPICS.items():
        path = CONV_DIR / f"{nid}.json"
        if not path.exists():
            print(f"  skip {nid}: file not found")
            continue
        conv = json.load(open(path))
        local = 0
        for s in conv.get("sessions", []):
            si = s.get("session_index")
            if si in topic_map and not s.get("topic"):
                if not args.dry_run:
                    s["topic"] = topic_map[si]
                local += 1
        n_added += local
        if not args.dry_run and local:
            path.write_text(json.dumps(conv, indent=2))
        print(f"  {nid}: {local} topics {'would be' if args.dry_run else ''} added")
    mode = "would add" if args.dry_run else "added"
    print(f"\nTotal: {mode} {n_added} session topics")


if __name__ == "__main__":
    main()
