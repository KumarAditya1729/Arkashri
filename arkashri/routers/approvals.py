# pyre-ignore-all-errors

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from arkashri.db import get_session
from arkashri.models import (
    ClientRole,
    ApprovalRequest,
    ApprovalAction,
    AuditRunStep,
    ApprovalStatus,
    ApprovalActionType,
    AuditStepStatus,
)
from arkashri.schemas import (
    ApprovalRequestCreate,
    ApprovalRequestOut,
    ApprovalActionCreate,
    ApprovalEscalationResponse,
)
from arkashri.dependencies import require_api_client, AuthContext, _append_and_publish_audit, _load_approval_with_actions, DEFAULT_APPROVAL_ESCALATION_MINUTES

router = APIRouter()

@router.post("/requests", response_model=ApprovalRequestOut, status_code=status.HTTP_201_CREATED)
async def create_approval_request(
    payload: ApprovalRequestCreate,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> ApprovalRequest:
    if payload.requested_by != auth.client_name:
        raise HTTPException(status_code=403, detail="requested_by must match authenticated API client")
    if payload.step_id is not None:
        step = await session.scalar(select(AuditRunStep).where(AuditRunStep.id == payload.step_id))
        if step is None:
            raise HTTPException(status_code=404, detail="Referenced run step not found")

    request = ApprovalRequest(
        tenant_id=payload.tenant_id,
        jurisdiction=payload.jurisdiction,
        request_type=payload.request_type,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        requested_by=payload.requested_by,
        reason=payload.reason,
        current_level=1,
        required_level=payload.required_level,
        status=ApprovalStatus.PENDING,
        payload=payload.payload,
        step_id=payload.step_id,
    )
    session.add(request)
    await session.flush()

    action = ApprovalAction(
        request_id=request.id,
        action_type=ApprovalActionType.SUBMITTED,
        actor_id=payload.requested_by,
        notes="Manual approval request created.",
        action_payload={"source": "api"},
    )
    session.add(action)

    await _append_and_publish_audit(
        session,
        tenant_id=payload.tenant_id,
        jurisdiction=payload.jurisdiction,
        event_type="APPROVAL_REQUEST_CREATED",
        entity_type="approval_request",
        entity_id=str(request.id),
        payload={
            "request_type": request.request_type,
            "reference_type": request.reference_type,
            "reference_id": request.reference_id,
            "required_level": request.required_level,
        },
    )

    await session.commit()
    stored = await _load_approval_with_actions(session, request.id)
    if stored is None:
        raise HTTPException(status_code=500, detail="Failed to load approval request after creation")
    return stored


@router.get("/{tenant_id}/{jurisdiction}", response_model=list[ApprovalRequestOut])
async def list_approval_requests(
    tenant_id: str,
    jurisdiction: str,
    status_filter: ApprovalStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> list[ApprovalRequestOut]:
    stmt = select(ApprovalRequest).where(
        ApprovalRequest.tenant_id == tenant_id,
        ApprovalRequest.jurisdiction == jurisdiction,
    )
    if status_filter:
        stmt = stmt.where(ApprovalRequest.status == status_filter)
    stmt = stmt.order_by(ApprovalRequest.opened_at.desc()).limit(limit)

    request_ids = list(await session.scalars(stmt.with_only_columns(ApprovalRequest.id)))
    requests: list[ApprovalRequestOut] = []
    for req_id in request_ids:
        req = await _load_approval_with_actions(session, req_id)
        if req is not None:
            requests.append(ApprovalRequestOut.model_validate(req))
    return requests


@router.post("/requests/{request_id}/actions", response_model=ApprovalRequestOut)
async def action_approval_request(
    request_id: uuid.UUID,
    payload: ApprovalActionCreate,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.REVIEWER})),
) -> ApprovalRequest:
    request = await _load_approval_with_actions(session, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if request.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
        raise HTTPException(status_code=400, detail=f"Request already closed with status {request.status.value}")

    action = ApprovalAction(
        request_id=request.id,
        action_type=payload.action_type,
        actor_id=auth.client_name,
        notes=payload.notes,
        action_payload=payload.action_payload,
    )
    session.add(action)

    if payload.action_type == ApprovalActionType.APPROVED:
        if request.current_level >= request.required_level:
            request.status = ApprovalStatus.APPROVED
            request.closed_at = datetime.now(timezone.utc)
            request.decision_notes = payload.notes
            if request.step_id:
                await session.execute(
                    update(AuditRunStep).where(AuditRunStep.id == request.step_id).values(status=AuditStepStatus.COMPLETED)
                )
        else:
            request.current_level += 1
    elif payload.action_type == ApprovalActionType.REJECTED:
        request.status = ApprovalStatus.REJECTED
        request.closed_at = datetime.now(timezone.utc)
        request.decision_notes = payload.notes
        if request.step_id:
            await session.execute(
                update(AuditRunStep).where(AuditRunStep.id == request.step_id).values(status=AuditStepStatus.FAILED)
            )
    elif payload.action_type == ApprovalActionType.ESCALATED:
        request.status = ApprovalStatus.ESCALATED
        request.required_level += 1
    elif payload.action_type == ApprovalActionType.COMMENTED:
        pass

    await _append_and_publish_audit(
        session,
        tenant_id=request.tenant_id,
        jurisdiction=request.jurisdiction,
        event_type="APPROVAL_ACTION_RECORDED",
        entity_type="approval_request",
        entity_id=str(request.id),
        payload={
            "action_type": payload.action_type.value,
            "actor_id": auth.client_name,
            "new_status": request.status.value,
        },
    )

    await session.commit()
    updated = await _load_approval_with_actions(session, request.id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to load request after action")
    return updated


@router.post("/escalate/{tenant_id}/{jurisdiction}", response_model=ApprovalEscalationResponse)
async def escalate_overdue_approvals(
    tenant_id: str,
    jurisdiction: str,
    threshold_minutes: int = Query(default=DEFAULT_APPROVAL_ESCALATION_MINUTES, ge=1, le=10_080),
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.REVIEWER})),
) -> ApprovalEscalationResponse:
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)

    stmt = select(ApprovalRequest).where(
        ApprovalRequest.tenant_id == tenant_id,
        ApprovalRequest.jurisdiction == jurisdiction,
        ApprovalRequest.status == ApprovalStatus.PENDING,
        ApprovalRequest.opened_at <= cutoff_time,
    )
    overdue_requests = list(await session.scalars(stmt))

    escalated_ids = []
    for req in overdue_requests:
        req.status = ApprovalStatus.ESCALATED
        req.required_level += 1

        action = ApprovalAction(
            request_id=req.id,
            action_type=ApprovalActionType.ESCALATED,
            actor_id=auth.client_name,
            notes=f"Auto-escalated due to exceeding {threshold_minutes} minutes SLA.",
            action_payload={"trigger": "job", "cutoff_time": cutoff_time.isoformat()},
        )
        session.add(action)

        await _append_and_publish_audit(
            session,
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            event_type="APPROVAL_AUTO_ESCALATED",
            entity_type="approval_request",
            entity_id=str(req.id),
            payload={
                "threshold_minutes": threshold_minutes,
                "original_level": req.current_level,
                "new_required_level": req.required_level,
            },
        )
        escalated_ids.append(req.id)

    await session.commit()
    return ApprovalEscalationResponse(
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        escalated_count=len(escalated_ids),
        escalated_request_ids=escalated_ids,
    )
