# pyre-ignore-all-errors
from __future__ import annotations

import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import structlog

from arkashri.models import ForensicProfile
from arkashri.schemas import ForensicProfileCreate

log = structlog.get_logger()


async def upsert_forensic_profile(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
    payload: ForensicProfileCreate,
) -> ForensicProfile:
    """
    Create or update the Forensic Risk Profile for an engagement.
    Designed to be called multiple times as new anomaly signals are generated.
    """
    stmt = select(ForensicProfile).where(ForensicProfile.engagement_id == engagement_id)
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        log.info("forensic_profile.create", engagement_id=str(engagement_id), tenant_id=tenant_id)
        record = ForensicProfile(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            **payload.model_dump(),
        )
        session.add(record)
    else:
        log.info("forensic_profile.update", engagement_id=str(engagement_id), tenant_id=tenant_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(record, field, value)

    await session.commit()
    await session.refresh(record)
    return record
