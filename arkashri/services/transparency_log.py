# pyre-ignore-all-errors
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.models import TransparencyLogEntry
from arkashri.services.canonical import hash_object

logger = logging.getLogger("services.transparency_log")

class TransparencyLogService:
    """
    Append-only verifiable log.
    Simulates a Certificate Transparency style log. In production, this data would 
    be accessible publicly to allow auditing of inclusion proofs.
    """
    
    @classmethod
    async def append_event(cls, session: AsyncSession, entry_type: str, payload_dict: dict) -> TransparencyLogEntry:
        """Appends a new event and updates the Merkle tree state."""
        # Query latest to get previous_hash
        latest = (await session.scalars(
            select(TransparencyLogEntry).order_by(TransparencyLogEntry.id.desc()).limit(1)
        )).first()
        
        previous_hash = latest.payload_hash if latest else "0000000000000000000000000000000000000000000000000000000000000000"
        
        # New payload hash
        payload_hash = hash_object(payload_dict)
        
        # Combine with previous hash for simple chain consistency
        merkle_tree_state = hashlib.sha256((previous_hash + payload_hash).encode('utf-8')).hexdigest()
        
        entry = TransparencyLogEntry(
            entry_type=entry_type,
            payload_hash=payload_hash,
            previous_hash=previous_hash,
            merkle_tree_state=merkle_tree_state,
            timestamp=datetime.now(timezone.utc)
        )
        
        session.add(entry)
        await session.flush()
        return entry
        
transparency_log_service = TransparencyLogService()
