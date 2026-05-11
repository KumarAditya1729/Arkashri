# pyre-ignore-all-errors
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Resolve workflow_pack directory with multiple fallbacks.
# This ensures correctness whether running in Docker, dev, or site-packages.
_CANDIDATES = [
    Path("/app/workflow_pack"),                        # Docker: always the canonical path
    Path(os.environ.get("APP_ROOT", "/app")) / "workflow_pack",  # env override
]

_base_path = Path(__file__).resolve()
if len(_base_path.parents) > 2:
    _CANDIDATES.append(_base_path.parents[2] / "workflow_pack")
if len(_base_path.parents) > 5:
    _CANDIDATES.append(_base_path.parents[5] / "workflow_pack")

_resolved = next((p for p in _CANDIDATES if (p / "index.json").exists()), None)
if _resolved is None:
    # Log all tried paths so it's easy to debug in Railway logs
    tried = ", ".join(str(p) for p in _CANDIDATES)
    raise RuntimeError(
        f"workflow_pack not found. Tried: [{tried}]. "
        "Ensure the directory was copied into the Docker image."
    )

PACK_DIR: Path = _resolved
log.info("workflow_pack resolved: %s", PACK_DIR)

INDEX_PATH = PACK_DIR / "index.json"
CATALOG_PATH = PACK_DIR / "service_catalog.json"
LIFECYCLE_PATH = PACK_DIR / "master_lifecycle.json"

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


@lru_cache
def load_service_catalog() -> dict[str, Any]:
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"Audit service catalog not found at {CATALOG_PATH}")
    return _load_json(CATALOG_PATH)


def get_service_catalog_summary() -> dict[str, Any]:
    catalog = load_service_catalog()
    service_count = sum(len(division.get("services", [])) for division in catalog.get("divisions", []))
    return {
        **catalog,
        "division_count": len(catalog.get("divisions", [])),
        "service_count": service_count,
    }


@lru_cache
def load_master_lifecycle() -> dict[str, Any]:
    if not LIFECYCLE_PATH.exists():
        raise FileNotFoundError(f"Master audit lifecycle not found at {LIFECYCLE_PATH}")
    return _load_json(LIFECYCLE_PATH)


def get_master_lifecycle_summary() -> dict[str, Any]:
    lifecycle = load_master_lifecycle()
    return {
        **lifecycle,
        "phase_count": len(lifecycle.get("phases", [])),
        "specialized_overlay_count": len(lifecycle.get("specialized_overlays", [])),
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
