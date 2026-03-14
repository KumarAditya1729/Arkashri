# pyre-ignore-all-errors
from __future__ import annotations

from typing import Any

from arkashri.services.canonical import canonical_json, sha256_hex

ZERO_HASH = "0" * 64


def compute_event_hash(prev_hash: str, chain_payload: dict[str, Any]) -> str:
    material = f"{prev_hash}{canonical_json(chain_payload)}"
    return sha256_hex(material)
