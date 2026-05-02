"""
Run GPT-4o-mini cleanup on residual session-leaky questions that the regex
pipeline could not handle.

Strict prompt: remove session refs, preserve the question's meaning, output
the cleaned question only — no preamble, no quotes.
"""
import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

SYSTEM_PROMPT = """You are cleaning question text in a social-memory benchmark dataset.

Each question references "Session N" or similar — these are corpus-internal artifacts that real users would never use. Rewrite each question to:

1. REMOVE all "Session N", "Sessions N-M", "Session 1", etc. references
2. PRESERVE the question's exact meaning and what is being asked
3. Replace temporal session refs with natural phrasing ("earlier", "later", "in the conversation", "across the conversations")
4. Keep all named entities (people, topics, events) exactly as they appear
5. Output ONLY the cleaned question — no quotes, no preamble, no explanation

If you cannot remove the session ref without losing meaning, return the original question unchanged."""

USER_TEMPLATE = """Rewrite this question to remove all session-number references while preserving meaning:

{question}"""


ANY_SESSION_REF = re.compile(r'[Ss]ession\s*\d+', re.IGNORECASE)


def rewrite_one(question: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(question=question)},
        ],
        temperature=0,
        max_tokens=400,
    )
    out = resp.choices[0].message.content.strip()
    # Strip any wrapping quotes
    if out.startswith('"') and out.endswith('"'):
        out = out[1:-1]
    if out.startswith("'") and out.endswith("'"):
        out = out[1:-1]
    return out


def main():
    QA_DIR = Path("data/qa")
    rewrites_done = 0
    rewrites_failed = 0
    file_changes = []

    for f in sorted(QA_DIR.glob("*.jsonl")):
        if f.stem.endswith("_qc") or f.stem.startswith("_"):
            continue
        out_lines = []
        modified = False
        for line in open(f):
            if not line.strip():
                out_lines.append(line)
                continue
            d = json.loads(line)
            if not d.get("_rewrite_pending"):
                out_lines.append(line)
                continue

            q_orig = d.get("_original_question") or d.get("question", "")
            try:
                q_new = rewrite_one(q_orig)
                if ANY_SESSION_REF.search(q_new):
                    # Model failed to remove the ref; try with stronger directive
                    q_new = rewrite_one(q_orig + "\n\nIMPORTANT: Do NOT include 'Session N' or any session number in your output.")

                if ANY_SESSION_REF.search(q_new):
                    rewrites_failed += 1
                    print(f"FAILED [{d.get('qa_id')}]: {q_new[:100]}")
                    out_lines.append(line)
                    continue

                d["question"] = q_new
                d["_rewrite_kind"] = "residual"
                d.pop("_rewrite_pending", None)
                rewrites_done += 1
                modified = True
                file_changes.append({
                    "qa_id": d.get("qa_id"),
                    "before": q_orig,
                    "after": q_new,
                })
            except Exception as e:
                print(f"ERROR [{d.get('qa_id')}]: {e}")
                out_lines.append(line)
                continue

            out_lines.append(json.dumps(d, ensure_ascii=False) + "\n")

        if modified:
            with open(f, "w") as fp:
                fp.writelines(out_lines)

    print(f"\nRewrites successful: {rewrites_done}")
    print(f"Rewrites failed:     {rewrites_failed}")

    # Append to existing change log
    log_path = Path("data/qa/_rewrite_log.json")
    existing = []
    if log_path.exists():
        existing = json.load(open(log_path))
    for ch in file_changes:
        existing.append({**ch, "kind": "residual"})
    with open(log_path, "w") as fp:
        json.dump(existing, fp, indent=2)
    print(f"Change log updated: {log_path}")

    print("\nFirst 5 residual rewrites:")
    for ch in file_changes[:5]:
        print(f"  BEFORE: {ch['before'][:160]}")
        print(f"  AFTER:  {ch['after'][:160]}")
        print()


if __name__ == "__main__":
    main()
