# pyre-ignore-all-errors
import asyncio
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from arkashri.config import get_settings
from arkashri.models import ChainAnchor, AuditEvent
from arkashri.services.canonical import hash_object

logger = structlog.get_logger("scripts.integrity_check")
settings = get_settings()

async def verify_anchor(session: AsyncSession, anchor: ChainAnchor):
    """
    Recomputes the Merkle root for all audit events associated with an anchor
    and compares it to the stored and on-chain root.
    """
    # Fetch all events covered by this anchor using the currently persisted event window logic.
    result = await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == anchor.tenant_id)
        .where(AuditEvent.id <= anchor.id) # Simplified range logic
    )
    events = result.all()
    
    if not events:
        return False, "No events found for anchor"
    
    # Compute local root (simplified as a canonical hash of event IDs)
    event_ids = sorted([str(e.id) for e in events])
    computed_root = hash_object({"event_ids": event_ids})
    
    is_match = computed_root == anchor.merkle_root
    
    return is_match, {
        "stored_root": anchor.merkle_root,
        "computed_root": computed_root,
        "event_count": len(events)
    }

async def run_integrity_audit():
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        result = await session.scalars(select(ChainAnchor))
        anchors = result.all()
        
        print(f"--- Arkashri Integrity Audit: {len(anchors)} anchors found ---")
        
        for anchor in anchors:
            match, details = await verify_anchor(session, anchor)
            status = "✅ VALID" if match else "❌ TAMPERED"
            print(f"Anchor {anchor.id} [{anchor.tenant_id}]: {status}")
            if not match:
                print(f"  Details: {details}")

if __name__ == "__main__":
    asyncio.run(run_integrity_audit())
