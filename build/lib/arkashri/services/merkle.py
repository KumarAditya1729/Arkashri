from __future__ import annotations

from arkashri.services.canonical import sha256_hex
from arkashri.services.hash_chain import ZERO_HASH


def merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return ZERO_HASH

    level = [item for item in hashes]
    while len(level) > 1:
        next_level: list[str] = []
        for index in range(0, len(level), 2):
            left = level[index]
            right = level[index + 1] if index + 1 < len(level) else left
            next_level.append(sha256_hex(f"{left}{right}"))
        level = next_level

    return level[0]
