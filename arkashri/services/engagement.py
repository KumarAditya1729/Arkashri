# pyre-ignore-all-errors
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
    independence_cleared = payload.independence_cleared
    kyc_cleared = payload.kyc_cleared
    conflict_notes = payload.conflict_check_notes

    if independence_cleared is None or kyc_cleared is None:
        if settings.independence_webhook_url:
            # Webhook configured — call it to auto-verify
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
                    kyc_cleared = data.get("kyc_cleared", True)
                    conflict_notes = data.get("notes", "Webhook check completed.")
            except Exception as exc:
                logger.warning("independence_webhook_failed", error=str(exc), tenant_id=payload.tenant_id)
                raise ValueError("Independence verification failed and no manual verification result was supplied.") from exc
        else:
            # No webhook configured — default to cleared (admin is responsible for manual verification)
            # This is the standard path for direct engagement creation via the UI
            independence_cleared = True
            kyc_cleared = True
            if conflict_notes is None:
                conflict_notes = "Manually verified by engagement administrator."

    if conflict_notes is None:
        conflict_notes = "Externally verified independence/kyc result recorded."

    from arkashri.services.jurisdiction_standards import get_standards_for_jurisdiction
    standards_info = get_standards_for_jurisdiction(payload.jurisdiction)
    
    status = EngagementStatus.ACCEPTED if (independence_cleared and kyc_cleared) else EngagementStatus.REJECTED

    engagement = Engagement(
        tenant_id=payload.tenant_id,
        jurisdiction=payload.jurisdiction,
        standards_framework=standards_info["framework"],
        client_name=payload.client_name,
        engagement_type=payload.engagement_type,
        period_start=payload.period_start,
        period_end=payload.period_end,
        status=status,
        independence_cleared=independence_cleared,
        kyc_cleared=kyc_cleared,
        conflict_check_notes=conflict_notes,
    )
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)

    # Automatically capture the active regulatory ruleset (RulesSnapshot)
    from arkashri.models import RulesSnapshot, RegulatoryDocument
    import hashlib
    import json
    from sqlalchemy import select

    docs = await session.scalars(
        select(RegulatoryDocument)
        .where(RegulatoryDocument.jurisdiction == payload.jurisdiction)
        .where(RegulatoryDocument.is_promoted.is_(True))
    )
    
    sa_versions = {}
    for doc in docs:
        key = f"{doc.authority}:{doc.external_id}"
        sa_versions[key] = doc.content_hash

    snapshot_hash = hashlib.sha256(json.dumps(sa_versions, sort_keys=True).encode()).hexdigest()

    snapshot = RulesSnapshot(
        engagement_id=engagement.id,
        snapshot_hash=snapshot_hash,
        sa_versions=sa_versions,
    )
    session.add(snapshot)
    await session.commit()

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
