"""
Fill options and correct_option for existing MC and short_answer QA pairs.

Q2/Q4/Q6 (multiple_choice): build A/B/C/D options from group member names,
  derive correct_option by finding which member name is named first/prominently
  in the answer text.

Q7 (short_answer): set correct_option to a short relationship phrase extracted
  from the first sentence of the answer.
"""

import json
import re
import random
from pathlib import Path

BASE = Path(__file__).parent.parent

MC_TYPES = {"Q2", "Q4", "Q6"}
LETTERS = ["A", "B", "C", "D", "E"]


def find_correct_member(answer: str, members: list[str], query_type: str = "Q4"):
    """Return the member name that is the correct answer."""
    # Q2/Q6: look for dissenter-specific patterns first, then fall back to first-mention
    # Q4: look for "NAME said it" / "NAME. When" patterns
    if query_type in ("Q2", "Q6"):
        for name in members:
            dissenter_patterns = [
                rf"—\s*{re.escape(name)}",
                rf"No\s*—\s*{re.escape(name)}",
                rf"Not for {re.escape(name)}",
                rf"{re.escape(name)} was the exception",
                rf"{re.escape(name)} is an exception",
                rf"{re.escape(name)} didn't",
                rf"{re.escape(name)} does not",
                rf"{re.escape(name)} cannot",
                rf"{re.escape(name)} can't",
                rf"not necessarily.*{re.escape(name)}",
                rf"{re.escape(name)} may not",
            ]
            for pat in dissenter_patterns:
                if re.search(pat, answer, re.IGNORECASE):
                    return name

    # Q4 and fallback: find first prominent mention
    best = None
    best_pos = len(answer) + 1
    for name in members:
        priority_patterns = [
            rf"—\s*{re.escape(name)}",
            rf"Not for {re.escape(name)}",
            rf"\b{re.escape(name)} said\b",
            rf"\b{re.escape(name)}\.\s",
            rf"\b{re.escape(name)}\b",
        ]
        for pat in priority_patterns:
            m = re.search(pat, answer, re.IGNORECASE)
            if m and m.start() < best_pos:
                best_pos = m.start()
                best = name
                break
    return best


def build_options(members: list[str], correct: str) -> tuple[dict, str]:
    """Return (options dict, correct letter). Options are alphabetical by name."""
    choices = sorted(members[:4])  # max 4 options
    if correct not in choices:
        # Replace last alphabetically with correct if not present
        choices[-1] = correct
        choices = sorted(choices)
    options = {LETTERS[i]: name for i, name in enumerate(choices)}
    correct_letter = next(k for k, v in options.items() if v == correct)
    return options, correct_letter


def extract_relationship(answer: str) -> str:
    """Extract a short relationship label from a Q7 answer."""
    # Look for relationship keywords in the first two sentences
    keywords = [
        r"mentor.{0,10}ment(?:ee|or)", r"childhood friends?", r"siblings?",
        r"closest pair", r"close(?:st)? friends?", r"hiking allies?",
        r"quiet allies?", r"institutional \w+", r"organis\w+ \w+",
        r"street \w+", r"founding \w+",
    ]
    text = " ".join(answer.split(".")[:2])
    for kw in keywords:
        m = re.search(kw, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    # Fallback: first clause before comma or dash
    first = re.split(r"[,—]", answer)[0].strip()
    return first[:50] if len(first) > 50 else first


def migrate_qa_file(path: Path, members: list[str]) -> int:
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    updated = []
    changed = 0
    for line in lines:
        pair = json.loads(line)
        qt = pair.get("query_type")
        fmt = pair.get("answer_format")

        # Reset previously-filled incorrect values too, so we recompute cleanly
        if fmt == "multiple_choice" and qt in MC_TYPES:
            correct_name = find_correct_member(pair["answer"], members, qt)
            if correct_name:
                options, correct_letter = build_options(members, correct_name)
                pair["options"] = options
                pair["correct_option"] = correct_letter
                changed += 1
            else:
                print(f"    WARNING: could not find correct name in {pair['qa_id']}")

        elif fmt == "short_answer" and qt == "Q7":
            pair["correct_option"] = extract_relationship(pair["answer"])
            changed += 1

        updated.append(json.dumps(pair, ensure_ascii=False))

    path.write_text("\n".join(updated) + "\n")
    return changed


def main():
    qa_dir = BASE / "data" / "qa"
    raw_dir = BASE / "data" / "raw"

    for qa_path in sorted(qa_dir.glob("*.jsonl")):
        network_id = qa_path.stem
        raw_path = raw_dir / f"{network_id}.json"
        if not raw_path.exists():
            print(f"  {network_id}: raw not found — skipping")
            continue
        net = json.loads(raw_path.read_text())
        members = [p["display_name"] for p in net["personas"]]
        n = migrate_qa_file(qa_path, members)
        print(f"  {network_id}: {n} pairs updated (members: {members})")

    print("\nDone.")


if __name__ == "__main__":
    main()
