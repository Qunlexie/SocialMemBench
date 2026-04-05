"""
Migration: add absolute date fields to existing conversation JSON files.

Adds to each file:
  - corpus.start_date       (ISO 8601 date string)
  - session.date            (ISO 8601 date string, one per session)
  - session.date_label      (updated to include full date, e.g. "Session 1, Monday January 6, 2025 11:23am")
  - turn.timestamp          (ISO 8601 datetime string)
  - turn.timestamp_label    (updated short form, e.g. "Jan 6, 11:23am")

Idempotent: skips any file that already has start_date set.

Usage:
    python scripts/migrate_add_dates.py
"""

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

# Assign a start_date (Monday) for each corpus, one per month
START_DATES: dict[str, str] = {
    "grp_1a2b3c4d": "2025-01-06",
    "grp_2b3c4d5e": "2025-02-03",
    "grp_3c4d5e6f": "2025-03-03",
    "grp_4d5e6f7a": "2025-04-07",
    "grp_5e6f7a8b": "2025-05-05",
    "grp_6f7a8b9c": "2025-06-02",
    "grp_7a8b9c0d": "2025-07-07",
    "grp_8b9c0d1e": "2025-08-04",
    "grp_9c0d1e2f": "2025-09-01",
    "grp_0d1e2f3a": "2025-10-06",
}

CONVERSATIONS_DIR = Path(__file__).parent.parent / "data" / "conversations"


def parse_time_from_label(label: str):
    """
    Extract (hour, minute) from a timestamp_label like "Session 1, 11:23am" or "Session 3, 2:47pm".
    Returns None if no time found.
    """
    match = re.search(r"(\d{1,2}):(\d{2})(am|pm)", label, re.IGNORECASE)
    if not match:
        return None
    hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(3).lower()
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    return hour, minute


def format_date_label(session_index: int, session_date: date, time_str: str) -> str:
    """
    Build a new date_label like "Session 1, Monday January 6, 2025 11:23am".
    time_str is e.g. "11:23am".
    """
    day_name = session_date.strftime("%A")
    month_name = session_date.strftime("%B")
    day_num = session_date.day
    year = session_date.year
    return f"Session {session_index}, {day_name} {month_name} {day_num}, {year} {time_str}"


def format_short_timestamp_label(session_date: date, time_str: str) -> str:
    """
    Build short form like "Jan 6, 11:23am".
    """
    month_abbr = session_date.strftime("%b")
    day_num = session_date.day
    return f"{month_abbr} {day_num}, {time_str}"


def migrate_file(path: Path, start_date_str: str) -> None:
    with open(path) as f:
        corpus = json.load(f)

    if corpus.get("start_date"):
        print(f"  skipping {path.name} — already has start_date")
        return

    start = date.fromisoformat(start_date_str)
    corpus["start_date"] = start_date_str

    for session in corpus["sessions"]:
        idx = session["session_index"]
        session_date = start + timedelta(weeks=idx - 1)
        session["date"] = session_date.isoformat()

        # Extract time from the first turn's timestamp_label to use in date_label
        first_turn_label = session["turns"][0]["timestamp_label"] if session["turns"] else ""
        time_parsed = parse_time_from_label(first_turn_label)
        if time_parsed:
            h, m = time_parsed
            meridiem = "am" if h < 12 else "pm"
            display_h = h if h <= 12 else h - 12
            if display_h == 0:
                display_h = 12
            time_str = f"{display_h}:{m:02d}{meridiem}"
        else:
            time_str = "12:00pm"

        session["date_label"] = format_date_label(idx, session_date, time_str)

        for turn in session["turns"]:
            label = turn["timestamp_label"]
            t = parse_time_from_label(label)
            if t:
                h, m = t
                dt = datetime(session_date.year, session_date.month, session_date.day, h, m)
                turn["timestamp"] = dt.isoformat()
                # Rebuild meridiem display
                meridiem = "am" if h < 12 else "pm"
                display_h = h if h <= 12 else h - 12
                if display_h == 0:
                    display_h = 12
                time_str_turn = f"{display_h}:{m:02d}{meridiem}"
                turn["timestamp_label"] = format_short_timestamp_label(session_date, time_str_turn)
            else:
                turn["timestamp"] = None

    with open(path, "w") as f:
        json.dump(corpus, f, indent=2, ensure_ascii=False)

    n_sessions = len(corpus["sessions"])
    n_turns = sum(len(s["turns"]) for s in corpus["sessions"])
    print(f"  migrated {path.name}: {n_sessions} sessions, {n_turns} turns")


def main() -> None:
    print(f"Migrating conversation files in {CONVERSATIONS_DIR}\n")
    for network_id, start_date in START_DATES.items():
        path = CONVERSATIONS_DIR / f"{network_id}.json"
        if not path.exists():
            print(f"  {network_id}.json not found — skipping")
            continue
        migrate_file(path, start_date)
    print("\nDone.")


if __name__ == "__main__":
    main()
