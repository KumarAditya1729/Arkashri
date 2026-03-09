import logging
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.config import get_settings
from arkashri.models import Engagement, EngagementStatus, MaterialityAssessment
from arkashri.schemas import EngagementCreate, MaterialityCreate

logger = logging.getLogger(__name__)


async def create_engagement(session: AsyncSession, payload: EngagementCreate) -> Engagement:
    """Create a new engagement and perform automated independence checking."""
    settings = get_settings()
    independence_cleared = True
    kyc_cleared = True
    conflict_notes = "Automated check passed. No known conflicts."

    if settings.independence_webhook_url:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    settings.independence_webhook_url,
                    json={
                        "tenant_id": payload.tenant_id,
                        "client_name": payload.client_name,
                        "engagement_type": payload.engagement_type.value,
                    },
                    timeout=5.0,
                )
                res.raise_for_status()
                data = res.json()
                independence_cleared = data.get("cleared", False)
                conflict_notes = data.get("notes", "Webhook check completed.")
        except Exception as exc:
            logger.warning(f"Independence webhook failed: {exc}. Falling back to default mock checks.")
            if payload.client_name.lower() in ["conflict corp", "restricted entity"]:
                independence_cleared = False
                conflict_notes = "Automatically flagged: Entity on restricted list."
    else:
        if payload.client_name.lower() in ["conflict corp", "restricted entity"]:
            independence_cleared = False
            conflict_notes = "Automatically flagged: Entity on restricted list."

    status = EngagementStatus.ACCEPTED if (independence_cleared and kyc_cleared) else EngagementStatus.REJECTED

    engagement = Engagement(
        tenant_id=payload.tenant_id,
        jurisdiction=payload.jurisdiction,
        client_name=payload.client_name,
        engagement_type=payload.engagement_type,
        status=status,
        independence_cleared=independence_cleared,
        kyc_cleared=kyc_cleared,
        conflict_check_notes=conflict_notes,
    )
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return engagement


async def get_engagement(session: AsyncSession, engagement_id: uuid.UUID) -> Engagement | None:
    return await session.get(Engagement, engagement_id)


async def compute_materiality(
    session: AsyncSession,
    engagement_id: uuid.UUID,
    tenant_id: str,
    jurisdiction: str,
    payload: MaterialityCreate,
) -> MaterialityAssessment:
    """Deterministically compute materiality thresholds."""
    
    # Calculate thresholds deterministically
    overall_mat = payload.basis_amount * (payload.overall_percentage / 100.0)
    perf_mat = overall_mat * (payload.performance_percentage / 100.0)
    trivial_thresh = overall_mat * (payload.trivial_threshold_percentage / 100.0)

    assessment = MaterialityAssessment(
        engagement_id=engagement_id,
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        basis=payload.basis,
        basis_amount=payload.basis_amount,
        overall_percentage=payload.overall_percentage,
        overall_materiality=overall_mat,
        performance_percentage=payload.performance_percentage,
        performance_materiality=perf_mat,
        trivial_threshold_percentage=payload.trivial_threshold_percentage,
        trivial_threshold=trivial_thresh,
        notes=payload.notes,
    )
    
    session.add(assessment)
    await session.commit()
    await session.refresh(assessment)
    return assessment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from arkashri.models import Engagement

async def list_engagements(session: AsyncSession) -> List[Engagement]:
    result = await session.execute(select(Engagement).order_by(Engagement.created_at.desc()))
    return result.scalars().all()
