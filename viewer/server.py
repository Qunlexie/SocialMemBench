"""SocialMemBench Viewer — FastAPI server.

Reads ../data/ (relative to this file) and serves JSON via API.
Also serves the static frontend from ./static/.

Run:
    cd viewer && python3 server.py
    open http://localhost:8080          # review viewer
    open http://localhost:8080/judge    # blinded human-judge annotation
"""

import csv
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = Path(__file__).parent
DATA_DIR = Path(os.environ.get("SMB_DATA_DIR", str(HERE.parent / "data")))

app = FastAPI(title="SocialMemBench Viewer")

# ── Static files ──────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/networks")
def list_networks():
    """Return a list of all available networks (from data/raw/*.json)."""
    raw_dir = DATA_DIR / "raw"
    if not raw_dir.exists():
        return JSONResponse([])

    networks = []
    for f in sorted(raw_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            networks.append({
                "network_id": data.get("network_id", f.stem),
                "group_name": data.get("group_name", f.stem),
                "group_type": data.get("group_type", "unknown"),
                "group_size": data.get("group_size", 0),
                "has_conversations": (DATA_DIR / "conversations" / f.name).exists(),
                "has_qa": (DATA_DIR / "qa" / f"{f.stem}.jsonl").exists(),
            })
        except Exception:
            pass
    return JSONResponse(networks)


@app.get("/api/network/{network_id}")
def get_network(network_id: str):
    """Return the full EgoNetwork JSON for a given network_id."""
    path = DATA_DIR / "raw" / f"{network_id}.json"
    if not path.exists():
        raise HTTPException(404, f"Network {network_id} not found")
    return JSONResponse(json.loads(path.read_text()))


@app.get("/api/conversations/{network_id}")
def get_conversations(network_id: str):
    """Return the ConversationCorpus JSON for a given network_id."""
    path = DATA_DIR / "conversations" / f"{network_id}.json"
    if not path.exists():
        raise HTTPException(404, f"Conversations for {network_id} not found")
    return JSONResponse(json.loads(path.read_text()))


@app.get("/api/qa/{network_id}")
def get_qa(network_id: str):
    """Return all QAPairs from the JSONL file for a given network_id."""
    path = DATA_DIR / "qa" / f"{network_id}.jsonl"
    if not path.exists():
        raise HTTPException(404, f"QA for {network_id} not found")
    pairs = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                pairs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return JSONResponse(pairs)


# ── Human-judge annotation (blinded) ──────────────────────────────────────────
# Serves data/human_judge/annotation_sheet.csv one row at a time and saves scores
# back to it. Never reads the key file, so condition and judge score stay hidden.

JUDGE_SHEET = DATA_DIR / "human_judge" / "annotation_sheet.csv"
JUDGE_CONTEXT = DATA_DIR / "human_judge" / "item_context.json"
JUDGE_FIELDS = ["item", "question", "gold_answer", "system_answer", "human_score", "notes", "checklist"]


class JudgeScore(BaseModel):
    human_score: Optional[float] = None
    notes: str = ""
    checklist: str = ""


def read_judge_rows() -> list:
    if not JUDGE_SHEET.exists():
        raise HTTPException(404, "No annotation sheet; run scripts/human_judge_agreement.py sample")
    with open(JUDGE_SHEET, newline="") as f:
        return list(csv.DictReader(f))


@app.get("/judge")
def judge_page():
    return FileResponse(HERE / "static" / "judge.html")


@app.get("/api/judge/items")
def judge_items():
    return JSONResponse(read_judge_rows())


@app.get("/api/judge/context")
def judge_context():
    """Gold-side context per item (question type, evidence anchors); no system or judge fields."""
    if not JUDGE_CONTEXT.exists():
        return JSONResponse({})
    return JSONResponse(json.loads(JUDGE_CONTEXT.read_text()))


@app.post("/api/judge/items/{item}")
def save_judge_score(item: str, body: JudgeScore):
    rows = read_judge_rows()
    row = next((r for r in rows if r["item"] == item), None)
    if row is None:
        raise HTTPException(404, f"Item {item} not found")
    if body.human_score is not None and not 0.0 <= body.human_score <= 1.0:
        raise HTTPException(422, "human_score must be between 0.0 and 1.0")
    row["human_score"] = "" if body.human_score is None else f"{body.human_score:.1f}"
    row["notes"] = body.notes
    row["checklist"] = body.checklist
    tmp = JUDGE_SHEET.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=JUDGE_FIELDS, restval="")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(JUDGE_SHEET)
    return JSONResponse(row)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    uvicorn.run("server:app", host=args.host, port=args.port, reload=False)
