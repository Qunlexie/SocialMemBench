"""
Question-text rewriting pipeline: strip session-number leakage.

Stages:
1. Strip compound clauses ("— and in which session...")
2. Strip standalone session refs (prefix, parenthetical, mid-sentence)
3. Naturalize temporal session refs (before/after Session N → earlier/later)
4. Grammar repair (capitalize, collapse spaces, fix orphan commas)
5. Final regex check: zero [Ss]ession\s*\d+ in question text

Outputs to data/qa/{network_id}.jsonl, replacing in place.
Tags each modified pair with metadata: rewrite_kind = cosmetic | semantic | temporal | residual.
"""
import json
import glob
import re
from pathlib import Path

QA_DIR = Path('data/qa')

# === Patterns ===

# B: Semantic — compound clauses being stripped (drops a sub-question)
COMPOUND_CLAUSE = re.compile(
    r'\s*[—–\-]{1,2}\s*(?:and\s+)?(?:in which session|what (?:in|does|did) Session\s*\d+|how does Session\s*\d+|what in Sessions?\s*\d+(?:\s*[-–]\s*\d+)?).*?(?=[?.!]|$)',
    re.IGNORECASE
)

# B2: "in which session" used as the main interrogative
IN_WHICH_SESSION = re.compile(r'\bin which session\b', re.IGNORECASE)

# A: Cosmetic — score-preserving artifact strips
PREFIX_IN_SESSION = re.compile(r'^\s*In\s+Sessions?\s*\d+(?:\s*(?:and|through|to|[-–])\s*\d+)?\s*,\s*', re.IGNORECASE)
PARENTHETICAL = re.compile(r'\s*\(\s*Sessions?\s*\d+\s*\)\s*', re.IGNORECASE)
MID_IN_SESSION = re.compile(r'\b(?:in|during|from|at)\s+Sessions?\s*\d+\b', re.IGNORECASE)

# C: Temporal — replace with natural language
SESSION_AND_LATER = re.compile(r'\bSessions?\s*\d+\s+and\s+(?:later|after|onwards?|beyond)\b', re.IGNORECASE)
BEFORE_SESSION_N = re.compile(r'\bbefore\s+Session\s*\d+\b', re.IGNORECASE)
AFTER_SESSION_N = re.compile(r'\bafter\s+Session\s*\d+\b', re.IGNORECASE)
SINCE_SESSION_N = re.compile(r'\bsince\s+Session\s*\d+\b', re.IGNORECASE)
UNTIL_SESSION_N = re.compile(r'\b(?:until|by)\s+Session\s*\d+\b', re.IGNORECASE)
PRIOR_TO_SESSION = re.compile(r'\bprior\s+to\s+Session\s*\d+\b', re.IGNORECASE)
SESSIONS_RANGE = re.compile(r'\bSessions?\s*\d+\s*(?:through|to|[-–])\s*\d+\b', re.IGNORECASE)
SESSIONS_LIST = re.compile(r'\bSessions?\s*\d+(?:\s*,\s*\d+){1,}(?:\s*,?\s*and\s*\d+)?\b', re.IGNORECASE)

# Final detection
ANY_SESSION_REF = re.compile(r'[Ss]ession\s*\d+', re.IGNORECASE)
IN_WHICH_SESSION_RES = re.compile(r'\bin which session', re.IGNORECASE)


def repair_grammar(s: str) -> str:
    """Fix artifacts left by clause/word removal."""
    # Replace orphaned "that session" / "those sessions" references that refer
    # to a session ref we just stripped
    s = re.sub(r'\bin that session\b', 'in the conversation', s, flags=re.IGNORECASE)
    s = re.sub(r'\bin those sessions?\b', 'in the conversations', s, flags=re.IGNORECASE)
    s = re.sub(r'\bof that session\b', 'of the conversation', s, flags=re.IGNORECASE)
    s = re.sub(r'\bduring that session\b', 'in the conversation', s, flags=re.IGNORECASE)
    s = re.sub(r'\bfrom that session\b', 'from the conversation', s, flags=re.IGNORECASE)

    # De-duplicate stop words created by adjacent regex substitutions
    s = re.sub(r'\b(across|in|during|by|after|before|since|until)\s+\1\b', r'\1', s, flags=re.IGNORECASE)
    s = re.sub(r'\bacross\s+across\b', 'across', s, flags=re.IGNORECASE)

    # Collapse multiple spaces
    s = re.sub(r'\s+', ' ', s)
    # Strip leading whitespace
    s = s.strip()
    # Strip orphan leading comma
    s = re.sub(r'^,\s*', '', s)
    # Fix double commas
    s = re.sub(r',\s*,', ',', s)
    # Fix space before punctuation
    s = re.sub(r'\s+([?.!,])', r'\1', s)
    # Capitalize first letter
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    # Ensure ends with terminal punctuation; default ?
    if s and s[-1] not in '?.!':
        s += '?'
    # Remove duplicate question marks
    s = re.sub(r'\?{2,}', '?', s)
    return s


def rewrite(question: str) -> tuple[str, str, str]:
    """
    Apply the regex pipeline.
    Returns (new_question, kind, original) where kind ∈ {unchanged, cosmetic, semantic, temporal, residual}.
    """
    if not ANY_SESSION_REF.search(question) and not IN_WHICH_SESSION_RES.search(question):
        return question, 'unchanged', question

    original = question
    kind = None
    q = question

    # Stage 1: Strip compound clauses (semantic — drops a sub-question)
    new_q, n = COMPOUND_CLAUSE.subn('', q)
    if n > 0:
        # Add back terminal punctuation if compound strip removed it
        if not new_q.rstrip().endswith(('?', '.', '!')):
            new_q = new_q.rstrip() + '?'
        q = new_q
        kind = 'semantic'

    # Stage 2: Strip prefix "In Session N, ..."
    new_q, n = PREFIX_IN_SESSION.subn('', q)
    if n > 0:
        q = new_q
        if kind is None:
            kind = 'cosmetic'

    # Stage 2b: Strip parenthetical (Session N)
    new_q, n = PARENTHETICAL.subn(' ', q)
    if n > 0:
        q = new_q
        if kind is None:
            kind = 'cosmetic'

    # Stage 3: Naturalize temporal refs (before substitution to capture order)
    for pat, repl, marker in [
        (SESSION_AND_LATER, 'later', 'temporal'),
        (BEFORE_SESSION_N, 'earlier', 'temporal'),
        (AFTER_SESSION_N, 'later', 'temporal'),
        (SINCE_SESSION_N, 'since then', 'temporal'),
        (UNTIL_SESSION_N, 'by then', 'temporal'),
        (PRIOR_TO_SESSION, 'earlier', 'temporal'),
        (SESSIONS_RANGE, 'across multiple conversations', 'temporal'),
        (SESSIONS_LIST, 'across multiple conversations', 'temporal'),
    ]:
        new_q, n = pat.subn(repl, q)
        if n > 0:
            q = new_q
            if kind is None or kind == 'cosmetic':
                kind = marker

    # Stage 4: Strip mid-sentence "in Session N", "during Session N", etc.
    new_q, n = MID_IN_SESSION.subn('', q)
    if n > 0:
        q = new_q
        if kind is None:
            kind = 'cosmetic'

    # Stage 5: Replace "in which session" with natural query
    new_q, n = IN_WHICH_SESSION.subn('where in the conversation', q)
    if n > 0:
        q = new_q
        if kind is None:
            kind = 'semantic'

    # Stage 6: Grammar repair
    q = repair_grammar(q)

    # Final check: any remaining session refs → mark as residual for LLM cleanup
    if ANY_SESSION_REF.search(q):
        return original, 'residual', original

    if q == original:
        return original, 'unchanged', original

    return q, kind or 'cosmetic', original


def main():
    all_changes = []
    file_count = 0
    total_pairs = 0
    by_kind = {'unchanged': 0, 'cosmetic': 0, 'semantic': 0, 'temporal': 0, 'residual': 0}

    for f in sorted(QA_DIR.glob('*.jsonl')):
        if f.stem.endswith('_qc'):
            continue
        file_count += 1
        out_lines = []
        modified = False
        for line in open(f):
            if not line.strip():
                out_lines.append(line)
                continue
            d = json.loads(line)
            total_pairs += 1
            q_orig = d.get('question', '')
            q_new, kind, _ = rewrite(q_orig)
            by_kind[kind] += 1

            if kind == 'unchanged':
                out_lines.append(line)
                continue

            if kind == 'residual':
                # Mark for LLM pass; keep original for now
                d['_rewrite_pending'] = True
                d['_original_question'] = q_orig
            else:
                d['question'] = q_new
                d['_rewrite_kind'] = kind
                d['_original_question'] = q_orig
                modified = True
                all_changes.append({
                    'qa_id': d.get('qa_id'),
                    'network_id': d.get('network_id'),
                    'kind': kind,
                    'before': q_orig,
                    'after': q_new,
                })

            out_lines.append(json.dumps(d, ensure_ascii=False) + '\n')

        if modified:
            with open(f, 'w') as fp:
                fp.writelines(out_lines)

    print(f'Files processed: {file_count}')
    print(f'Total pairs: {total_pairs}')
    print(f'By kind: {by_kind}')
    print(f'\nFirst 5 cosmetic changes:')
    for c in [c for c in all_changes if c['kind'] == 'cosmetic'][:5]:
        print(f'  BEFORE: {c["before"][:130]}')
        print(f'  AFTER:  {c["after"][:130]}')
        print()
    print(f'\nFirst 3 semantic changes:')
    for c in [c for c in all_changes if c['kind'] == 'semantic'][:3]:
        print(f'  BEFORE: {c["before"][:200]}')
        print(f'  AFTER:  {c["after"][:200]}')
        print()
    print(f'\nFirst 3 temporal changes:')
    for c in [c for c in all_changes if c['kind'] == 'temporal'][:3]:
        print(f'  BEFORE: {c["before"][:200]}')
        print(f'  AFTER:  {c["after"][:200]}')
        print()

    # Save change log
    log_path = Path('data/qa/_rewrite_log.json')
    with open(log_path, 'w') as fp:
        json.dump(all_changes, fp, indent=2)
    print(f'\nChange log saved to {log_path}')


if __name__ == '__main__':
    main()
