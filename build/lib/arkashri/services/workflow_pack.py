# pyre-ignore-all-errors
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
PACK_DIR = ROOT_DIR / "workflow_pack"
INDEX_PATH = PACK_DIR / "index.json"



def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))



def _ensure_relative_to_pack(path: Path) -> None:
    try:
        path.relative_to(PACK_DIR)
    except ValueError as exc:  # pragma: no cover
        raise ValueError("Template path escapes workflow pack directory") from exc



@lru_cache
def load_workflow_pack_index() -> dict[str, Any]:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"Workflow pack index not found at {INDEX_PATH}")
    return _load_json(INDEX_PATH)



def get_workflow_pack_summary() -> dict[str, Any]:
    index = load_workflow_pack_index()
    return {
        "pack_id": index["pack_id"],
        "version": index["version"],
        "schema": index["schema"],
        "templates": index["templates"],
    }



def load_workflow_template(audit_type: str) -> dict[str, Any]:
    index = load_workflow_pack_index()
    entry = next((item for item in index["templates"] if item["audit_type"] == audit_type), None)
    if entry is None:
        raise KeyError(f"Unknown audit type: {audit_type}")

    template_path = (PACK_DIR / entry["path"]).resolve()
    _ensure_relative_to_pack(template_path)

    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found for audit type '{audit_type}'")

    return _load_json(template_path)
