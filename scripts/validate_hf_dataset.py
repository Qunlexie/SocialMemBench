"""
validate_hf_dataset.py — comprehensive validator for the SocialMemBench HuggingFace
release. Run after every `build_hf_dataset.py --write` to catch schema violations,
FK breaks, semantic invariant failures, and JSON-encoding bugs before upload.

Exit code 0 = all checks pass. Non-zero = fix the data and re-emit before pushing.

Usage:
    python scripts/validate_hf_dataset.py
    python scripts/validate_hf_dataset.py --hf-dir hf_dataset
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

DEFAULT_HF_DIR = Path(__file__).resolve().parents[1] / "hf_dataset"

REQUIRED_TABLES = ("networks", "personas", "conversations", "qa")

# Per-table required (always populated) columns. Anything in this list MUST have
# zero null values across all rows. Columns not listed here are allowed nulls
# only if they are semantically optional (e.g. options_json on a non-MC question).
REQUIRED_NON_NULL = {
    "networks": ["network_id", "group_name", "group_type", "group_size", "tier",
                 "n_personas", "edges_json", "group_norms_json", "metadata_json"],
    "personas": ["network_id", "persona_id", "display_name", "age", "gender",
                 "communication_profile_json"],
    "conversations": ["network_id", "session_id", "session_index", "session_topic",
                      "session_date_label", "session_date", "turn_id",
                      "speaker_persona_id", "speaker_display_name", "message",
                      "timestamp", "timestamp_label", "message_index"],
    "qa": ["qa_id", "network_id", "query_type", "difficulty", "question", "answer",
           "answer_format", "evidence_anchors_json", "qc_phase1_score",
           "qc_phase2_grounded", "qc_phase3_flagged", "generation_seed",
           "metadata_json"],
}

# Columns where empty-string / empty-list / empty-object IS semantically correct,
# i.e., the empty value truthfully represents "no value applies for this row".
# Reviewers should NOT interpret these as missing data.
SEMANTIC_EMPTY_OK = {
    "networks": {
        "metadata_json": "{} when no extra generation metadata recorded",
    },
    "personas": {
        "preference_history_json": "[] when persona has no historical preference shifts recorded",
    },
    "conversations": {
        "reply_to_turn_id": "'' when a turn isn't a reply",
        "active_participants_json": "[] when session metadata didn't record an explicit attendance list",
    },
    "qa": {
        "options_json": "[] for non-multiple-choice questions",
        "correct_option": "'' for non-multiple-choice questions",
        "contamination_foil": "'' for non-Q4 questions",
        "temporal_anchors_json": "[] for non-Q8 questions",
        "source_challenge_id": "'' when QA pair predates challenge-id linkage (~3% of corpus)",
    },
}


# Columns whose values must parse as valid JSON.
JSON_COLUMNS = {
    "networks": ["edges_json", "group_norms_json", "metadata_json"],
    "personas": ["big_five_json", "communication_profile_json", "preferences_json",
                 "preference_history_json", "speaking_quirks_json", "skills_list_json"],
    "conversations": ["active_participants_json"],
    "qa": ["options_json", "evidence_anchors_json", "temporal_anchors_json",
           "metadata_json"],
}


class Issue:
    def __init__(self, severity: str, table: str, message: str):
        self.severity = severity
        self.table = table
        self.message = message
    def __repr__(self):
        return f"[{self.severity}][{self.table}] {self.message}"


def load_tables(hf_dir: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for tbl in REQUIRED_TABLES:
        path = hf_dir / f"{tbl}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Missing parquet: {path}")
        out[tbl] = pd.read_parquet(path)
    return out


def check_no_nulls_in_required(tables: dict, issues: list[Issue]) -> None:
    for tbl, cols in REQUIRED_NON_NULL.items():
        df = tables[tbl]
        for c in cols:
            if c not in df.columns:
                issues.append(Issue("FAIL", tbl, f"missing required column: {c}"))
                continue
            n_null = df[c].isna().sum()
            if n_null > 0:
                issues.append(Issue("FAIL", tbl, f"required column '{c}' has {n_null} null values"))


def check_json_valid(tables: dict, issues: list[Issue]) -> None:
    for tbl, cols in JSON_COLUMNS.items():
        df = tables[tbl]
        for c in cols:
            if c not in df.columns: continue
            for idx, val in df[c].items():
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    continue
                if not isinstance(val, str):
                    issues.append(Issue("WARN", tbl, f"column '{c}' row {idx}: expected string, got {type(val).__name__}"))
                    continue
                try:
                    json.loads(val)
                except json.JSONDecodeError as e:
                    issues.append(Issue("FAIL", tbl, f"column '{c}' row {idx}: invalid JSON ({e})"))


def check_fk_consistency(tables: dict, issues: list[Issue]) -> None:
    """Every network_id in personas/conversations/qa must exist in networks."""
    network_ids = set(tables["networks"]["network_id"].unique())
    for tbl in ("personas", "conversations", "qa"):
        df = tables[tbl]
        if "network_id" not in df.columns:
            issues.append(Issue("FAIL", tbl, "missing network_id column"))
            continue
        missing = set(df["network_id"].unique()) - network_ids
        if missing:
            issues.append(Issue("FAIL", tbl, f"network_id values not in networks table: {sorted(missing)[:5]}{'...' if len(missing)>5 else ''}"))


def check_count_invariants(tables: dict, issues: list[Issue]) -> None:
    """Every network has ≥1 persona, ≥1 session-turn, ≥1 QA pair."""
    netw = tables["networks"]
    for nid in netw["network_id"]:
        for tbl, label in [("personas", "personas"), ("conversations", "turns"), ("qa", "QA pairs")]:
            n = (tables[tbl]["network_id"] == nid).sum()
            if n == 0:
                issues.append(Issue("FAIL", tbl, f"network {nid} has 0 {label}"))

    # n_personas in networks should match actual count
    for nid in netw["network_id"]:
        declared = int(netw.loc[netw["network_id"] == nid, "n_personas"].iloc[0])
        actual = int((tables["personas"]["network_id"] == nid).sum())
        if declared != actual:
            issues.append(Issue("WARN", "networks", f"network {nid}: n_personas declares {declared}, personas table has {actual}"))


def check_value_ranges(tables: dict, issues: list[Issue]) -> None:
    qa = tables["qa"]
    if "qc_phase1_score" in qa.columns:
        bad = qa[(qa["qc_phase1_score"] < 0) | (qa["qc_phase1_score"] > 1.0)]
        if len(bad):
            issues.append(Issue("FAIL", "qa", f"qc_phase1_score out of [0,1] for {len(bad)} rows"))
    netw = tables["networks"]
    if "tier" in netw.columns:
        valid_tiers = {"small", "medium", "large"}
        bad = set(netw["tier"].dropna()) - valid_tiers
        if bad:
            issues.append(Issue("FAIL", "networks", f"unknown tier values: {sorted(bad)}"))
    if "group_size" in netw.columns:
        bad = netw[netw["group_size"] < 3]
        if len(bad):
            issues.append(Issue("WARN", "networks", f"group_size < 3 for {len(bad)} networks"))


def check_semantic_empties_documented(tables: dict, issues: list[Issue]) -> None:
    """For every column with empty values, ensure SEMANTIC_EMPTY_OK or REQUIRED_NON_NULL covers it.
    Empty values appearing in undocumented columns are flagged for review."""
    for tbl, df in tables.items():
        documented_cols = set(SEMANTIC_EMPTY_OK.get(tbl, {}).keys())
        required_cols = set(REQUIRED_NON_NULL.get(tbl, []))
        for c in df.columns:
            if df[c].dtype != object:
                continue
            empty_n = ((df[c] == "") | (df[c] == "[]") | (df[c] == "{}")).sum()
            if empty_n > 0 and c not in documented_cols and c not in required_cols:
                issues.append(Issue("WARN", tbl, f"undocumented empty values in '{c}': {empty_n} rows. "
                                                 "Add to SEMANTIC_EMPTY_OK or REQUIRED_NON_NULL."))




def check_em_dashes_in_messages(tables: dict, issues: list[Issue]) -> None:
    """No em-dash (—) should appear in conversation message fields."""
    df = tables.get("conversations")
    if df is None or "message" not in df.columns: return
    em_count = df["message"].str.contains("—", regex=False, na=False).sum()
    if em_count:
        issues.append(Issue("FAIL", "conversations", f"{em_count} messages contain em-dash (—) — run scripts/scrub_em_dashes.py"))

def check_qc_aggregate(tables: dict, issues: list[Issue]) -> None:
    """Corpus-wide QC sanity."""
    qa = tables["qa"]
    if "qc_phase1_score" in qa.columns:
        below = (qa["qc_phase1_score"] < 0.7).sum()
        mean = float(qa["qc_phase1_score"].mean())
        if mean < 0.85:
            issues.append(Issue("WARN", "qa", f"corpus blind-critic mean below 0.85 ({mean:.3f})"))
        if below > len(qa) * 0.05:
            issues.append(Issue("WARN", "qa", f"more than 5% of pairs below 0.70 ({below}/{len(qa)})"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hf-dir", default=str(DEFAULT_HF_DIR))
    args = ap.parse_args()

    hf_dir = Path(args.hf_dir)
    print(f"Validating: {hf_dir}")
    tables = load_tables(hf_dir)
    for tbl, df in tables.items():
        print(f"  {tbl}: shape={df.shape}, cols={len(df.columns)}")

    issues: list[Issue] = []
    check_no_nulls_in_required(tables, issues)
    check_json_valid(tables, issues)
    check_fk_consistency(tables, issues)
    check_count_invariants(tables, issues)
    check_value_ranges(tables, issues)
    check_semantic_empties_documented(tables, issues)
    check_em_dashes_in_messages(tables, issues)
    check_qc_aggregate(tables, issues)

    fails = [i for i in issues if i.severity == "FAIL"]
    warns = [i for i in issues if i.severity == "WARN"]
    print(f"\nIssues: {len(fails)} FAIL, {len(warns)} WARN")
    for i in issues:
        print(f"  {i}")

    if fails:
        print("\n❌ Validation FAILED. Fix the issues above before uploading to HuggingFace.")
        sys.exit(1)
    print("\n✓ Validation PASSED. Dataset is HF-upload ready.")
    sys.exit(0)


if __name__ == "__main__":
    main()
