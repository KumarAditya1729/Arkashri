# pyre-ignore-all-errors
from __future__ import annotations

import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import structlog

from arkashri.models import ESGMetrics
from arkashri.schemas import ESGMetricsCreate

log = structlog.get_logger()


async def upsert_esg_metrics(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
    payload: ESGMetricsCreate,
) -> ESGMetrics:
    """
    Create or update ESG metrics for an engagement.
    If a record already exists for the engagement, it will be updated in place.
    """
    stmt = select(ESGMetrics).where(ESGMetrics.engagement_id == engagement_id)
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        log.info("esg_metrics.create", engagement_id=str(engagement_id), tenant_id=tenant_id)
        record = ESGMetrics(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            **payload.model_dump(),
        )
        session.add(record)
    else:
        log.info("esg_metrics.update", engagement_id=str(engagement_id), tenant_id=tenant_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(record, field, value)

    await session.commit()
    await session.refresh(record)
    return record
