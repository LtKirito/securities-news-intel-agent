from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def create_run_dir(run_id: str) -> Path:
    path = DATA_DIR / "research_runs" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path
