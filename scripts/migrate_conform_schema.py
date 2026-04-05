"""
Migration: conform existing data to current schema.

QA files (data/qa/*.jsonl):
  - Add answer_format based on query_type
  - Add options: null, correct_option: null (MC/short values need Claude to fill)
  - Remove skill_version field

Raw network files (data/raw/*.json):
  - Add occupation: null (Claude fills per persona from background)
  - Add skills_list: [] (Claude fills per persona)

Idempotent: skips QA lines that already have answer_format set.
"""

import json
from pathlib import Path

BASE = Path(__file__).parent.parent

ANSWER_FORMATS = {
    "Q1": "long_form",
    "Q2": "multiple_choice",
    "Q3": "long_form",
    "Q4": "multiple_choice",
    "Q5": "long_form",
    "Q6": "multiple_choice",
    "Q7": "short_answer",
    "Q8": "long_form",
}


def migrate_qa_file(path: Path) -> int:
    lines = path.read_text().splitlines()
    updated = []
    changed = 0
    for line in lines:
        if not line.strip():
            continue
        pair = json.loads(line)
        if "answer_format" not in pair:
            pair["answer_format"] = ANSWER_FORMATS.get(pair.get("query_type", "Q1"), "long_form")
            pair.setdefault("options", None)
            pair.setdefault("correct_option", None)
            changed += 1
        pair.pop("skill_version", None)
        updated.append(json.dumps(pair, ensure_ascii=False))
    path.write_text("\n".join(updated) + "\n")
    return changed


def migrate_raw_file(path: Path) -> int:
    network = json.loads(path.read_text())
    changed = 0
    for persona in network.get("personas", []):
        if "occupation" not in persona:
            persona["occupation"] = None
            changed += 1
        if "skills_list" not in persona:
            persona["skills_list"] = []
    if changed:
        path.write_text(json.dumps(network, indent=2, ensure_ascii=False))
    return changed


def main():
    qa_dir = BASE / "data" / "qa"
    raw_dir = BASE / "data" / "raw"

    print("QA files:")
    for p in sorted(qa_dir.glob("*.jsonl")):
        n = migrate_qa_file(p)
        print(f"  {p.name}: {n} pairs updated")

    print("\nRaw network files:")
    for p in sorted(raw_dir.glob("*.json")):
        n = migrate_raw_file(p)
        status = f"{n} personas updated" if n else "already conformant"
        print(f"  {p.name}: {status}")

    print("\nDone.")


if __name__ == "__main__":
    main()
