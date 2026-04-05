"""SocialMemBench Viewer — FastAPI server.

Reads ../data/ (relative to this file) and serves JSON via API.
Also serves the static frontend from ./static/.

Run:
    cd viewer && python server.py
    open http://localhost:8080
"""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    uvicorn.run("server:app", host=args.host, port=args.port, reload=False)
