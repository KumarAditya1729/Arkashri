# pyre-ignore-all-errors
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
import datetime
import uuid
from decimal import Decimal
from typing import Any, Set

# Fields where list order is NOT semantically meaningful and should be sorted.
# All other lists (Audit Logs, Transactions, Test Scripts) will preserve input order.
CANONICAL_UNORDERED_KEYS: Set[str] = {
    "partner_signatures",
    "overrides",
    "rule_snapshot_hash",
    "decision_overrides",
    "audit_opinions",
    "hashes",
}

def _canonical_number(v: float | int | Decimal) -> str:
    """
    RFC-compliant number normalization:
     - No scientific notation (0.00001 NOT 1e-05)
     - No trailing zeros (98.60 -> 98.6)
     - Safe for JS (strings used for all decimals)
    """
    if v is None:
        return "null"
    if isinstance(v, (float, Decimal)) and (math.isnan(v) or math.isinf(v)):
        return str(v)
    
    # Normalize removes trailing zeros, 'f' format prevents scientific notation
    d = Decimal(str(v)).normalize()
    return format(d, 'f')

def _canonical_value(v: object, key: str | None = None) -> object:
    """
    Recursive normalization for canonical JSON.
    Coerces all numbers to strict strings to ensure cross-language consistency.
    """
    if v is None:
        return None
    
    # Handle Dicts (sort keys)
    if isinstance(v, dict):
        return {
            unicodedata.normalize('NFC', str(k)): _canonical_value(val, k) 
            for k, val in sorted(v.items())
        }
    
    # Handle Lists (conditional sorting)
    if isinstance(v, list):
        items = [_canonical_value(i, key) for i in v]
        if key in CANONICAL_UNORDERED_KEYS:
            return sorted(
                items,
                key=lambda x: json.dumps(x, sort_keys=True, separators=(',',':'), ensure_ascii=True)
            )
        return items
    
    # Handle Numbers (Strict String Coercion)
    if isinstance(v, (float, Decimal, int)) and type(v) is not bool:
        return _canonical_number(v)
    
    # Handle Booleans
    if isinstance(v, bool):
        return v
    
    # Handle DateTime / Date
    if isinstance(v, datetime.datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=datetime.timezone.utc)
        return v.astimezone(datetime.timezone.utc).isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    
    # Handle UUIDs
    if isinstance(v, uuid.UUID):
        return str(v)
    
    # Standard String / Fallback
    res = unicodedata.normalize('NFC', str(v)) if isinstance(v, str) else v
    return res if isinstance(v, (str, bool)) else str(v)

def canonical_json_bytes(data: Any) -> bytes:
    """Produces the strict UTF-8 Byte Stream required for verifiers."""
    normalized = _canonical_value(data)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
        allow_nan=False,
    ).encode('utf-8')

def canonical_json(data: Any) -> str:
    """Returns the string representation of the canonical output."""
    return canonical_json_bytes(data).decode('utf-8')

def sha256_hex(payload: str | bytes) -> str:
    """Standard SHA-256 hex digest for internal string/bytes data."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def hash_object(data: Any) -> str:
    """Public utility: SHA-256 of canonicalized object."""
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()
