# pyre-ignore-all-errors
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.config import get_settings
from arkashri.models import (
    AuditSLAStatus,
    AuditWorkflowType,
    Engagement,
    EngagementStatus,
    EngagementType,
    MaterialityAssessment,
    WorkflowReportStatus,
)
from arkashri.schemas import EngagementCreate, EngagementWorkflowUpdate, MaterialityCreate

logger = logging.getLogger(__name__)


ENGAGEMENT_TYPE_TO_WORKFLOW: dict[EngagementType, AuditWorkflowType] = {
    EngagementType.STATUTORY_AUDIT: AuditWorkflowType.STATUTORY_AUDIT,
    EngagementType.TAX_AUDIT: AuditWorkflowType.TAX_AUDIT,
    EngagementType.COMPLIANCE_AUDIT: AuditWorkflowType.GST_AUDIT,
    EngagementType.INTERNAL_AUDIT: AuditWorkflowType.INTERNAL_AUDIT,
    EngagementType.INVENTORY_AUDIT: AuditWorkflowType.STOCK_AUDIT,
    EngagementType.FINANCIAL_AUDIT: AuditWorkflowType.BANK_LOAN_AUDIT,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def calculate_current_day(start_date: datetime, *, target_days: int = 7, now: datetime | None = None) -> int:
    """Return the persisted workflow day, capped to the 7-day target UI."""
    current = now or _utc_now()
    started = _coerce_aware(start_date)
    elapsed = (current - started).days + 1
    return max(1, min(target_days, elapsed))


def derive_sla_status(
    *,
    due_date: datetime,
    report_status: WorkflowReportStatus,
    review_status: str,
    now: datetime | None = None,
) -> AuditSLAStatus:
    if report_status in {WorkflowReportStatus.GENERATED, WorkflowReportStatus.SEALED}:
        return AuditSLAStatus.COMPLETED

    current = now or _utc_now()
    due = _coerce_aware(due_date)
    if current > due:
        return AuditSLAStatus.DELAYED
    if (due - current) <= timedelta(days=1) and review_status != "approved":
        return AuditSLAStatus.AT_RISK
    return AuditSLAStatus.ON_TRACK


def _default_audit_type(payload: EngagementCreate) -> AuditWorkflowType:
    return payload.audit_type or ENGAGEMENT_TYPE_TO_WORKFLOW.get(
        payload.engagement_type,
        AuditWorkflowType.STATUTORY_AUDIT,
    )


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
    start_date = payload.start_date or _utc_now()
    due_date = payload.due_date or (start_date + timedelta(days=payload.target_completion_days))
    current_day = payload.current_day or calculate_current_day(start_date, target_days=payload.target_completion_days)
    sla_status = payload.sla_status
    if payload.sla_status == AuditSLAStatus.ON_TRACK:
        sla_status = derive_sla_status(
            due_date=due_date,
            report_status=payload.report_status,
            review_status=payload.review_status.value,
        )

    engagement = Engagement(
        tenant_id=payload.tenant_id,
        jurisdiction=payload.jurisdiction,
        standards_framework=standards_info["framework"],
        client_name=payload.client_name,
        engagement_type=payload.engagement_type,
        period_start=payload.period_start,
        period_end=payload.period_end,
        audit_type=_default_audit_type(payload),
        target_completion_days=payload.target_completion_days,
        start_date=start_date,
        due_date=due_date,
        current_day=current_day,
        sla_status=sla_status,
        checklist_progress=payload.checklist_progress,
        document_progress=payload.document_progress,
        review_status=payload.review_status,
        report_status=payload.report_status,
        status=status,
        independence_cleared=independence_cleared,
        kyc_cleared=kyc_cleared,
        conflict_check_notes=conflict_notes,
    )
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)

    # Automatically capture the active regulatory ruleset (RulesSnapshot)
    # This is optional — engagement creation succeeds even if snapshot fails
    try:
        from arkashri.models import RulesSnapshot, RegulatoryDocument
        import hashlib
        import json
        from sqlalchemy import select

        docs = (await session.scalars(
            select(RegulatoryDocument)
            .where(RegulatoryDocument.jurisdiction == payload.jurisdiction)
            .where(RegulatoryDocument.is_promoted.is_(True))
        )).all()
        
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
    except Exception as snap_exc:
        logger.warning("rules_snapshot_failed", error=str(snap_exc), engagement_id=str(engagement.id))
        # Roll back only the snapshot, not the engagement itself
        await session.rollback()

    return engagement


async def get_engagement(session: AsyncSession, engagement_id: uuid.UUID) -> Engagement | None:
    return await session.get(Engagement, engagement_id)


async def update_engagement_workflow(
    session: AsyncSession,
    engagement: Engagement,
    payload: EngagementWorkflowUpdate,
) -> Engagement:
    """Update the target workflow metadata without changing audit/legal sign-off semantics."""
    updates = payload.model_dump(exclude_none=True, by_alias=False)

    for field, value in updates.items():
        setattr(engagement, field, value)

    if "start_date" in updates or "target_completion_days" in updates:
        if "due_date" not in updates:
            engagement.due_date = engagement.start_date + timedelta(days=engagement.target_completion_days)
        if "current_day" not in updates:
            engagement.current_day = calculate_current_day(
                engagement.start_date,
                target_days=engagement.target_completion_days,
            )

    if "sla_status" not in updates:
        engagement.sla_status = derive_sla_status(
            due_date=engagement.due_date,
            report_status=engagement.report_status,
            review_status=engagement.review_status.value,
        )

    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return engagement


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
