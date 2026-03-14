# pyre-ignore-all-errors
"""
services/password.py — Password hashing and verification
=========================================================
Uses bcrypt directly (not via passlib) for Python 3.14 compatibility.
passlib's bcrypt backend crashes on Python 3.14 due to a version detection
attribute change in bcrypt 4.x. Direct calls work on all versions.
"""
from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt. Store the result — never the plain text."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False
