# pyre-ignore-all-errors
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from arkashri.models import (
    Engagement, EngagementStatus, EvidenceRecord, Transaction, 
    ERPSyncLog, Decision, ProfessionalJudgment, JudgmentStatus
)

logger = logging.getLogger(__name__)

class WorkflowViolation(Exception):
    """Raised when an engagement does not meet criteria for a state transition."""
    pass

ALLOWED_TRANSITIONS = {
    # ACCEPTED is the initial writable state after engagement creation.
    # PENDING = not yet accepted. REJECTED = terminal. SEALED = terminal.
    EngagementStatus.ACCEPTED:  [EngagementStatus.COLLECTED, EngagementStatus.FLAGGED, EngagementStatus.REJECTED],
    EngagementStatus.COLLECTED: [EngagementStatus.VERIFIED, EngagementStatus.FLAGGED],
    EngagementStatus.VERIFIED:  [EngagementStatus.REVIEWED, EngagementStatus.FLAGGED],
    EngagementStatus.FLAGGED:   [EngagementStatus.COLLECTED, EngagementStatus.VERIFIED],
    EngagementStatus.REVIEWED:  [],   # SEALED is only reachable via seal service (generate_audit_seal)
    EngagementStatus.SEALED:    [],   # Immutable terminal state
    EngagementStatus.REJECTED:  [],   # Terminal state
    EngagementStatus.PENDING:   [EngagementStatus.ACCEPTED, EngagementStatus.REJECTED],
}

async def transition_engagement(
    session: AsyncSession, 
    engagement_id: uuid.UUID, 
    target_status: EngagementStatus,
    actor_id: str
) -> Engagement:
    """
    Handles state transitions for an audit engagement with business logic validation.
    Strictly enforces linear workflow and prevents bypasses.
    """
    engagement = await session.get(Engagement, engagement_id)
    if not engagement:
        raise ValueError("Engagement not found")

    current_status = engagement.status
    
    if current_status == target_status:
        return engagement

    # ── Strict Linearity Check ────────────────────────────────────────────────
    if target_status not in ALLOWED_TRANSITIONS.get(current_status, []):
        raise WorkflowViolation(
            f"Invalid transition Attempted: {current_status.value} -> {target_status.value}. "
            f"Must follow the sequence: PLANNING -> COLLECTED -> VERIFIED -> REVIEWED -> SEALED."
        )

    # ── Protection of the Seal ────────────────────────────────────────────────
    if target_status == EngagementStatus.SEALED:
        # In production, this status can only be set by services/seal.py
        # If this function is called with target_status=SEALED directly via API, 
        # it MUST be blocked unless we are in a migration/repair context (not documented here).
        raise WorkflowViolation(
            "Direct transition to SEALED is forbidden. Use the cryptographic seal endpoint (/api/v1/seal) "
            "to finalize and anchor the engagement."
        )

    # ── Readiness Validation ──────────────────────────────────────────────────
    if target_status == EngagementStatus.COLLECTED:
        await _verify_collected_readiness(session, engagement)
    elif target_status == EngagementStatus.VERIFIED:
        await _verify_verified_readiness(session, engagement)
    elif target_status == EngagementStatus.FLAGGED:
        await _verify_flagged_readiness(session, engagement)
    elif target_status == EngagementStatus.REVIEWED:
        await _verify_reviewed_readiness(session, engagement)
    
    # ── Update Status & Metadata ──────────────────────────────────────────────
    engagement.status = target_status
    
    metadata = engagement.state_metadata or {"history": [], "checklists": {}}
    if "history" not in metadata:
        metadata["history"] = []
    
    metadata["history"].append({
        "from": current_status.value,
        "to": target_status.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor_id
    })
    
    engagement.state_metadata = metadata
    
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    
    logger.info(f"Engagement {engagement_id} transitioned from {current_status} to {target_status} by {actor_id}")
    return engagement


async def _verify_collected_readiness(session: AsyncSession, engagement: Engagement):
    """Requires at least one ERP sync for this engagement's tenant connection and at least one evidence document."""
    # C-8: Must be scoped to ERPConnections belonging to this specific engagement's tenant.
    # Previously queried all ERPSyncLogs for the tenant, allowing other engagements' syncs
    # to satisfy this gate. Now checks: is there a SUCCESSFUL/PARTIAL sync log for any
    # active connection under this tenant that was completed after the engagement was created?
    from arkashri.models import ERPConnection, ERPSyncStatus
    has_sync = (await session.scalar(
        select(func.count(ERPSyncLog.id))
        .join(ERPConnection, ERPSyncLog.connection_id == ERPConnection.id)
        .where(
            ERPConnection.tenant_id == engagement.tenant_id,
            ERPSyncLog.tenant_id == engagement.tenant_id,
            ERPSyncLog.status.in_([ERPSyncStatus.SUCCESS, ERPSyncStatus.PARTIAL]),
            ERPSyncLog.started_at >= engagement.created_at,  # sync must have happened after engagement creation
        )
    )) > 0

    if not has_sync:
        raise WorkflowViolation(
            "Cannot transition to COLLECTED: No successful ERP synchronization found after engagement creation. "
            "Run an ERP sync via POST /erp/connections/{id}/sync before transitioning."
        )

    has_evidence = (await session.scalar(
        select(func.count(EvidenceRecord.id)).where(EvidenceRecord.engagement_id == engagement.id)
    )) > 0

    if not has_evidence:
        raise WorkflowViolation("Cannot transition to COLLECTED: At least one evidence document is required.")


async def _verify_verified_readiness(session: AsyncSession, engagement: Engagement):
    """Requires evidence to be linked to audit tests."""
    has_tests = (await session.scalar(
        select(func.count(EvidenceRecord.id)).where(
            EvidenceRecord.engagement_id == engagement.id,
            EvidenceRecord.test_ref.is_not(None)
        )
    )) > 0
    
    if not has_tests:
        raise WorkflowViolation("Cannot transition to VERIFIED: No evidence has been linked to audit test references.")


async def _verify_flagged_readiness(session: AsyncSession, engagement: Engagement):
    """Requires at least one risk assessment run for the current engagement."""
    has_decisions = (await session.scalar(
        select(func.count(Decision.id))
        .join(Transaction, Decision.transaction_id == Transaction.id)
        .where(Transaction.tenant_id == engagement.tenant_id)
    )) > 0
    
    if not has_decisions:
        raise WorkflowViolation("Cannot transition to FLAGGED: No risk assessment decisions (Scoring) have been found.")


async def _verify_reviewed_readiness(session: AsyncSession, engagement: Engagement):
    """
    Requires:
      1. All ProfessionalJudgment records for this engagement to be SIGNED.
      2. At least one judgment to exist (cannot review an empty audit).
    """
    stmt = select(ProfessionalJudgment).where(ProfessionalJudgment.engagement_id == engagement.id)
    result = await session.execute(stmt)
    judgments = result.scalars().all()
    
    if not judgments:
        raise WorkflowViolation("Cannot transition to REVIEWED: No professional judgments have been recorded. Auditors must document their findings.")
        
    pending_judgments = [j for j in judgments if j.status == JudgmentStatus.PENDING]
    if pending_judgments:
        areas = ", ".join([j.area for j in pending_judgments])
        raise WorkflowViolation(f"Cannot transition to REVIEWED: PENDING judgments found in areas: {areas}. All findings must be signed.")

    logger.info(f"Readiness verified for Engagement {engagement.id}: {len(judgments)} judgments signed.")
