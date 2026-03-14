# pyre-ignore-all-errors
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import AuditEvent
from arkashri.services.hash_chain import ZERO_HASH, compute_event_hash


async def append_audit_event(
    session: AsyncSession,
    *,
    tenant_id: str,
    jurisdiction: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    signing_key_id: str | None = None,
    signature: str | None = None,
) -> AuditEvent:
    last_event = await session.scalar(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id, AuditEvent.jurisdiction == jurisdiction)
        .order_by(AuditEvent.id.desc())
        .limit(1)
    )
    prev_hash = last_event.event_hash if last_event else ZERO_HASH
    chain_payload = {
        "tenant_id": tenant_id,
        "jurisdiction": jurisdiction,
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payload": payload,
    }
    event_hash = compute_event_hash(prev_hash, chain_payload)

    event = AuditEvent(
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        prev_hash=prev_hash,
        event_hash=event_hash,
        signature_key_id=signing_key_id,
        signature=signature,
    )
    session.add(event)
    await session.flush()
    return event


async def verify_audit_chain(session: AsyncSession, tenant_id: str, jurisdiction: str) -> tuple[bool, list[str], int]:
    events = list(
        await session.scalars(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id, AuditEvent.jurisdiction == jurisdiction)
            .order_by(AuditEvent.id.asc())
        )
    )

    issues: list[str] = []
    prev_hash = ZERO_HASH

    for event in events:
        chain_payload = {
            "tenant_id": event.tenant_id,
            "jurisdiction": event.jurisdiction,
            "event_type": event.event_type,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "payload": event.payload,
        }
        expected_hash = compute_event_hash(prev_hash, chain_payload)

        if event.prev_hash != prev_hash:
            issues.append(
                f"event_id={event.id}: prev_hash mismatch (stored={event.prev_hash}, expected={prev_hash})"
            )
        if event.event_hash != expected_hash:
            issues.append(
                f"event_id={event.id}: event_hash mismatch (stored={event.event_hash}, expected={expected_hash})"
            )

        prev_hash = event.event_hash

    return (len(issues) == 0, issues, len(events))
