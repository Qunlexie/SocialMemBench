"""
build_hf_dataset.py — convert SocialMemBench data into a HuggingFace-friendly layout.

This script merges the three on-disk SocialMemBench data sources
    data/raw/{network_id}.json           # ego networks (Stage 1)
    data/conversations/{network_id}.json # conversation corpora (Stage 2)
    data/qa/{network_id}.jsonl           # QA pairs (Stage 3)
    data/qa/{network_id}_qc.json         # QC reports
    data/manifest.json                   # central manifest
into the layout HuggingFace expects for a multi-config dataset:

    hf_dataset/
        README.md                            # rendered from the Jinja template
        networks/train/networks.parquet      # one row per ego network (no personas)
        personas/train/personas.parquet      # one row per persona, indexed by network_id
        conversations/train/conversations.parquet  # one row per conversation turn
        qa/train/qa.parquet                  # one row per QA pair

Four configs are exposed (`networks`, `personas`, `conversations`, `qa`),
mirroring how EverMemBench-Dynamic is laid out on the Hub (configs `dialogues`,
`qars`, `profiles`). Personas are split out into their own table so they can
be loaded and joined to networks via `network_id` without forcing the
networks table to carry the full nested persona blob. We use parquet because
the Croissant auto-extractor on the Hub prefers parquet (it produces the
`refs/convert/parquet` branch automatically).

NOTE on planted_challenges: we deliberately *strip* the planted_challenges
field from the public turns table because it is the ground-truth signal for
QA generation; reviewers and downstream researchers should evaluate against
the public QA pairs, not against the leaked challenge index. The planted
challenges remain in the local repo under `data/conversations/` for
reproducibility.

Usage
-----
    python scripts/build_hf_dataset.py --dry-run   # default: report only
    python scripts/build_hf_dataset.py --write     # actually write parquet

The default is dry-run, per the project's data-quality discipline.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

# pandas + pyarrow are the standard route to parquet from a stdlib script.
# Guard the import so --dry-run still works without them installed.
try:
    import pandas as pd  # type: ignore
except ImportError:  # pragma: no cover
    pd = None  # type: ignore


# --------------------------------------------------------------------------- #
# Paths and configuration
# --------------------------------------------------------------------------- #

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CONV_DIR = DATA_DIR / "conversations"
QA_DIR = DATA_DIR / "qa"
MANIFEST_PATH = DATA_DIR / "manifest.json"

DEFAULT_OUT_DIR = REPO_ROOT / "hf_dataset"

# Four configs, one split each (`train`). Using `train` matches the
# EverMemBench convention; reviewers can split downstream as needed.
CONFIG_NETWORKS = "networks"
CONFIG_PERSONAS = "personas"
CONFIG_CONVERSATIONS = "conversations"
CONFIG_QA = "qa"
SPLIT = "data"  # neutral split name; benchmark has no train/test concept

# Fields stripped from the public release.
STRIP_FROM_TURNS = ("planted_challenges",)


# --------------------------------------------------------------------------- #
# Loading helpers
# --------------------------------------------------------------------------- #

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def discover_network_ids() -> list[str]:
    """Network IDs that have all three required artifacts (raw, conv, qa)."""
    raw_ids = {p.stem for p in RAW_DIR.glob("grp_*.json")}
    conv_ids = {p.stem for p in CONV_DIR.glob("grp_*.json")}
    qa_ids = {p.stem for p in QA_DIR.glob("grp_*.jsonl")}
    complete = sorted(raw_ids & conv_ids & qa_ids)
    return complete


# --------------------------------------------------------------------------- #
# Row builders
# --------------------------------------------------------------------------- #

def derive_tier(group_size: int | None) -> str | None:
    """Single source of truth for tier mapping. Matches socialmembench.config."""
    if not group_size: return None
    if group_size <= 6: return "small"
    if group_size <= 14: return "medium"
    return "large"


def build_network_row(network: dict, manifest_entry: dict | None) -> dict:
    """Flatten an EgoNetwork into one parquet row.

    Personas are NOT included here — they live in the dedicated `personas`
    table, indexed by `network_id`. Edges, group norms, and metadata stay
    nested (parquet `struct`/`list` types).
    """
    # Nested fields (edges, group_norms, metadata) can have heterogeneous shapes
    # across networks (e.g. closeness as "Medium" vs int). Serialize as JSON
    # strings so pyarrow gets a uniform string column at parquet-write time.
    group_size = network.get("group_size")
    # Derive tier from group_size if manifest doesn't have it (some older
    # networks lack manifest tier; tier itself is deterministic from size).
    tier = (manifest_entry or {}).get("tier") or derive_tier(group_size)
    # Trimmed to reviewer-essential columns. Internal generation metadata
    # (seed, manifest status) stays in the local repo and is not republished.
    return {
        "network_id": network["network_id"],
        "group_name": network.get("group_name"),
        "group_type": network.get("group_type"),
        "group_size": group_size,
        "tier": tier,
        "n_personas": len(network.get("personas", []) or []),
        "edges_json": json.dumps(network.get("edges", []), ensure_ascii=False),
        "group_norms_json": json.dumps(network.get("group_norms", []), ensure_ascii=False),
        "metadata_json": json.dumps(network.get("metadata", {}), ensure_ascii=False),
    }


def build_persona_rows(network: dict) -> Iterable[dict]:
    """One row per persona, foreign-keyed to `network_id`.

    Nested fields (big_five, communication_profile, preferences,
    preference_history) are kept as parquet structs/lists so reviewers can
    inspect the full persona spec without rejoining tables.
    """
    # group_name/group_type are redundant with the networks table (join on
    # network_id), so we don't repeat them here. Saves disk + matches peer
    # benchmark conventions (EverMemBench profiles).
    network_id = network["network_id"]
    for persona in network.get("personas", []) or []:
        yield {
            "network_id": network_id,
            "persona_id": persona.get("persona_id"),
            "display_name": persona.get("display_name"),
            "age": persona.get("age"),
            "gender": persona.get("gender"),
            "occupation": persona.get("occupation"),
            "background": persona.get("background"),
            "big_five_json": json.dumps(persona.get("big_five", {}), ensure_ascii=False),
            "communication_profile_json": json.dumps(persona.get("communication_profile", {}), ensure_ascii=False),
            "preferences_json": json.dumps(persona.get("preferences", {}), ensure_ascii=False),
            "preference_history_json": json.dumps(persona.get("preference_history", []), ensure_ascii=False),
            "speaking_quirks_json": json.dumps(persona.get("speaking_quirks", []), ensure_ascii=False),
            "skills_list_json": json.dumps(persona.get("skills_list", []), ensure_ascii=False),
        }


def build_conversation_rows(corpus: dict) -> Iterable[dict]:
    """One row per conversation turn (long form, easy to filter by network).

    Stripping `planted_challenges` keeps the public release honest — those
    fields are the ground-truth signal used to generate QA pairs.
    """
    from datetime import date as _date

    def _parse_iso_date(s):
        if not s: return None
        try:
            y, mo, d = s.split("-")
            return _date(int(y), int(mo), int(d))
        except Exception:
            return None

    network_id = corpus["network_id"]
    sessions = corpus.get("sessions", []) or []
    start_date = corpus.get("start_date")
    if not start_date and sessions:
        start_date = sessions[0].get("date")

    # Backfill gap_days from session.date deltas where missing.
    prev_date_obj = None
    session_gap_map = {}
    for session in sessions:
        sd = _parse_iso_date(session.get("date"))
        idx = session.get("session_index")
        if idx is None:
            continue
        if session.get("gap_days") is not None:
            session_gap_map[idx] = session["gap_days"]
        elif prev_date_obj and sd:
            session_gap_map[idx] = (sd - prev_date_obj).days
        else:
            session_gap_map[idx] = 0  # first session of corpus
        if sd:
            prev_date_obj = sd

    for session in sessions:
        s_idx = session.get("session_index")
        s_id = session.get("session_id")
        s_topic = session.get("topic") or (f"Session {s_idx}" if s_idx is not None else "Untitled session")
        s_date_label = session.get("date_label") or ""
        s_date = session.get("date") or ""
        gap_days = session_gap_map.get(s_idx, 0)
        active_participants = session.get("active_participants", []) or []

        for turn in session.get("turns", []):
            row = {
                "network_id": network_id,
                "session_id": s_id or f"{network_id}_s{s_idx:02d}" if s_idx is not None else f"{network_id}_unknown",
                "session_index": s_idx if s_idx is not None else 0,
                "session_topic": s_topic,
                "session_date_label": s_date_label,
                "session_date": s_date,
                "session_gap_days": int(gap_days),
                "active_participants_json": json.dumps(active_participants, ensure_ascii=False),
                "corpus_start_date": start_date or "",
                "turn_id": turn.get("turn_id") or "",
                "speaker_persona_id": turn.get("speaker_persona_id") or "",
                "speaker_display_name": turn.get("speaker_display_name") or "",
                "timestamp_label": turn.get("timestamp_label") or "",
                "timestamp": turn.get("timestamp") or "",
                "message": turn.get("message") or "",
                "message_index": turn.get("message_index") if turn.get("message_index") is not None else 0,
                "reply_to_turn_id": turn.get("reply_to_turn_id") or "",
            }
            for k in STRIP_FROM_TURNS:
                row.pop(k, None)
            yield row


def build_qa_rows(qa_records: Iterable[dict]) -> Iterable[dict]:
    """QA records are already flat enough; cast the nested `evidence_anchors`
    list as-is and surface the QC fields at the top level so reviewers can
    filter by qc_phase1_score, etc."""
    for qa in qa_records:
        # Nested fields (options, evidence_anchors, temporal_anchors, contamination_foil,
        # metadata) are heterogeneous across QA pairs (some have multiple_choice with
        # options list, others are short_answer with no options; some have temporal_anchors
        # only on Q8). Serialize as JSON strings for parquet uniformity.
        # Schema-uniform: no null cells. Empty-list/string/object defaults are
        # used for fields that don't apply to a given query_type (e.g. Q1 has
        # no contamination_foil — emit empty string rather than null).
        contam = qa.get("contamination_foil")
        if isinstance(contam, dict) or isinstance(contam, list):
            contam_str = json.dumps(contam, ensure_ascii=False)
        else:
            contam_str = contam or ""
        # group_id (redundant with network_id) and query_type_label
        # (already encoded by query_type) dropped for cleaner public schema.
        yield {
            "qa_id": qa.get("qa_id") or "",
            "network_id": qa.get("network_id") or "",
            "query_type": qa.get("query_type") or "",
            "difficulty": qa.get("difficulty") or "medium",
            "question": qa.get("question") or "",
            "answer": qa.get("answer") or "",
            "answer_format": qa.get("answer_format") or "long_form",
            "options_json": json.dumps(qa.get("options") or [], ensure_ascii=False),
            "correct_option": qa.get("correct_option") or "",
            "evidence_anchors_json": json.dumps(qa.get("evidence_anchors", []) or [], ensure_ascii=False),
            "contamination_foil": contam_str,
            "temporal_anchors_json": json.dumps(qa.get("temporal_anchors") or [], ensure_ascii=False),
            "qc_phase1_score": float(qa.get("qc_phase1_score") if qa.get("qc_phase1_score") is not None else 0.0),
            "qc_phase2_grounded": bool(qa.get("qc_phase2_grounded")),
            "qc_phase3_flagged": bool(qa.get("qc_phase3_flagged")),
            # qc_phase3_flag_reason intentionally excluded — currently no flagged
            # pairs in the corpus; reviewers can filter on qc_phase3_flagged if
            # future re-runs add structural flags.
            "source_challenge_id": qa.get("source_challenge_id") or "",
            "generation_seed": int(qa.get("generation_seed") if qa.get("generation_seed") is not None else 0),
            "metadata_json": json.dumps(qa.get("metadata", {}) or {}, ensure_ascii=False),
        }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

@dataclass
class BuildPlan:
    network_ids: list[str]
    n_networks: int
    n_personas: int
    n_conversations_files: int
    n_qa_files: int
    n_turns_estimated: int
    n_qa_pairs: int
    out_dir: Path

    def report(self) -> str:
        return "\n".join([
            "=" * 72,
            "SocialMemBench HuggingFace build plan",
            "=" * 72,
            f"  output dir         : {self.out_dir}",
            f"  configs            : {CONFIG_NETWORKS}, {CONFIG_PERSONAS}, {CONFIG_CONVERSATIONS}, {CONFIG_QA}",
            f"  split              : {SPLIT}",
            f"  networks (rows)    : {self.n_networks}",
            f"  personas (rows)    : {self.n_personas}",
            f"  conversations files: {self.n_conversations_files}",
            f"  turns (rows, est.) : {self.n_turns_estimated}",
            f"  qa rows            : {self.n_qa_pairs}",
            f"  network IDs        : {', '.join(self.network_ids[:5])}"
            + (" ..." if len(self.network_ids) > 5 else ""),
            "=" * 72,
        ])


def collect(
    network_ids: list[str], manifest: dict
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    networks_rows: list[dict] = []
    personas_rows: list[dict] = []
    conversations_rows: list[dict] = []
    qa_rows: list[dict] = []

    manifest_networks = manifest.get("networks", {})

    for nid in network_ids:
        network = load_json(RAW_DIR / f"{nid}.json")
        corpus = load_json(CONV_DIR / f"{nid}.json")
        qa_records = list(load_jsonl(QA_DIR / f"{nid}.jsonl"))

        networks_rows.append(build_network_row(network, manifest_networks.get(nid)))
        personas_rows.extend(build_persona_rows(network))
        conversations_rows.extend(build_conversation_rows(corpus))
        qa_rows.extend(build_qa_rows(qa_records))

    return networks_rows, personas_rows, conversations_rows, qa_rows


def write_parquet(rows: list[dict], out_path: Path) -> None:
    if pd is None:
        raise RuntimeError(
            "pandas is required for --write mode. Install with `pip install "
            "pandas pyarrow` or run with --dry-run."
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_parquet(out_path, index=False)


def write_jsonl(rows: list[dict], out_path: Path) -> None:
    """Optional jsonl mirror — useful for streaming consumers and `datasets`
    `streaming=True`. Off by default; flip on with --also-jsonl."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build HuggingFace-ready parquet from SocialMemBench data."
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUT_DIR}).",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="Actually write the files. Without this flag the script runs in dry-run "
             "mode and only reports what *would* be written.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run mode (no writes). This is the default; the flag is "
             "kept for clarity in CI logs.",
    )
    p.add_argument(
        "--also-jsonl",
        action="store_true",
        help="Also emit a jsonl mirror alongside each parquet (for streaming).",
    )
    p.add_argument(
        "--limit-networks",
        type=int,
        default=None,
        help="Process only the first N network IDs (debug aid).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Default behaviour is dry-run; --write must be explicit.
    dry_run = (not args.write) or args.dry_run

    if not MANIFEST_PATH.exists():
        print(f"ERROR: manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        return 2
    manifest = load_json(MANIFEST_PATH)

    network_ids = discover_network_ids()
    if args.limit_networks is not None:
        network_ids = network_ids[: args.limit_networks]

    if not network_ids:
        print("ERROR: no networks found with all three artifacts.", file=sys.stderr)
        return 2

    networks_rows, personas_rows, conversations_rows, qa_rows = collect(
        network_ids, manifest
    )

    plan = BuildPlan(
        network_ids=network_ids,
        n_networks=len(networks_rows),
        n_personas=len(personas_rows),
        n_conversations_files=len(network_ids),
        n_qa_files=len(network_ids),
        n_turns_estimated=len(conversations_rows),
        n_qa_pairs=len(qa_rows),
        out_dir=args.out_dir,
    )
    print(plan.report())

    out_paths = {
        CONFIG_NETWORKS: args.out_dir / CONFIG_NETWORKS / SPLIT / f"{CONFIG_NETWORKS}.parquet",
        CONFIG_PERSONAS: args.out_dir / CONFIG_PERSONAS / SPLIT / f"{CONFIG_PERSONAS}.parquet",
        CONFIG_CONVERSATIONS: args.out_dir / CONFIG_CONVERSATIONS / SPLIT / f"{CONFIG_CONVERSATIONS}.parquet",
        CONFIG_QA: args.out_dir / CONFIG_QA / SPLIT / f"{CONFIG_QA}.parquet",
    }

    print("\nFiles that would be written:")
    for cfg, path in out_paths.items():
        print(f"  [{cfg:14s}] -> {path}")
        if args.also_jsonl:
            print(f"  [{cfg + ' (jsonl)':14s}] -> {path.with_suffix('.jsonl')}")
    print(f"  [README        ] -> {args.out_dir / 'README.md'}  (render via Jinja template)")

    if dry_run:
        print("\nDRY-RUN: no files written. Re-run with --write to actually emit parquet.")
        return 0

    print("\nWriting parquet files...")
    write_parquet(networks_rows, out_paths[CONFIG_NETWORKS])
    write_parquet(personas_rows, out_paths[CONFIG_PERSONAS])
    write_parquet(conversations_rows, out_paths[CONFIG_CONVERSATIONS])
    write_parquet(qa_rows, out_paths[CONFIG_QA])

    if args.also_jsonl:
        print("Writing jsonl mirrors...")
        write_jsonl(networks_rows, out_paths[CONFIG_NETWORKS].with_suffix(".jsonl"))
        write_jsonl(personas_rows, out_paths[CONFIG_PERSONAS].with_suffix(".jsonl"))
        write_jsonl(conversations_rows, out_paths[CONFIG_CONVERSATIONS].with_suffix(".jsonl"))
        write_jsonl(qa_rows, out_paths[CONFIG_QA].with_suffix(".jsonl"))

    print("Done. Render the README separately via the Jinja template "
          "(scripts/build_hf_dataset_README.md.j2).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
