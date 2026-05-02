"""JSON / JSONL I/O utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from pydantic import BaseModel


def save_json(obj: Any, path: str | Path, indent: int = 2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, BaseModel):
        data = obj.model_dump(mode="json")
    else:
        data = obj
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def load_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_jsonl(
    records: Iterable[Any],
    path: str | Path,
    append: bool = False,
) -> int:
    """
    Write records to a JSONL file.
    append=True adds to existing file (for incremental runs).
    Returns number of records written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    count = 0
    with open(path, mode, encoding="utf-8") as f:
        for record in records:
            if isinstance(record, BaseModel):
                line = record.model_dump_json()
            else:
                line = json.dumps(record, ensure_ascii=False)
            f.write(line + "\n")
            count += 1
    return count


def load_jsonl(path: str | Path) -> Iterator[dict]:
    """Iterate over records in a JSONL file."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)
