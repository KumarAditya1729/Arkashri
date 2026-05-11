from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.dependencies import AuthContext, require_api_client
from arkashri.models import ClientRole
from arkashri.services.audit_automation import (
    AuditAutomationError,
    build_agent_run_pack,
    build_automation_pack,
    build_capability_matrix,
    build_sampling_plan,
    render_working_paper_html,
    run_big4_automation_pack,
    _engagement_transactions,
    _load_engagement,
)
from arkashri.services.audit import append_audit_event

router = APIRouter(prefix="/audit-automation", tags=["Big 4 Automation Engine"])


class AutomationRunRequest(BaseModel):
    create_risks: bool = True
    create_controls: bool = True
    persist_report: bool = True


class AutomationPackOut(BaseModel):
    engagement_id: str
    client_name: str
    audit_type: str
    standards_framework: str
    risk_intelligence: dict[str, Any]
    working_papers: dict[str, Any]
    report_readiness: dict[str, Any]


class AutomationRunOut(BaseModel):
    created_risk_count: int
    created_control_count: int
    report_job_id: str | None
    pack: AutomationPackOut


class SamplingRequest(BaseModel):
    sample_size: int = 25


class ConfirmationRequest(BaseModel):
    counterparty: str
    confirmation_type: str = "BALANCE_CONFIRMATION"
    amount: float | None = None
    due_date: str | None = None
    contact_email: str | None = None


class ManagementResponseRequest(BaseModel):
    finding_code: str
    response_text: str
    owner: str = "Management"
    target_date: str | None = None
    status: str = "OPEN"


def _parse_engagement_id(engagement_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(engagement_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID") from exc


@router.get("/engagements/{engagement_id}/pack", response_model=AutomationPackOut)
async def get_automation_pack(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> AutomationPackOut:
    try:
        pack = await build_automation_pack(
            session,
            tenant_id=auth.tenant_id,
            engagement_id=_parse_engagement_id(engagement_id),
        )
    except AuditAutomationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AutomationPackOut.model_validate(pack)


@router.get("/capabilities")
async def get_capabilities(
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> dict[str, Any]:
    return build_capability_matrix()


@router.post(
    "/engagements/{engagement_id}/run",
    response_model=AutomationRunOut,
    status_code=status.HTTP_201_CREATED,
)
async def run_automation_pack(
    engagement_id: str,
    payload: AutomationRunRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> AutomationRunOut:
    try:
        result = await run_big4_automation_pack(
            session,
            tenant_id=auth.tenant_id,
            engagement_id=_parse_engagement_id(engagement_id),
            actor=auth.client_name,
            create_risks=payload.create_risks,
            create_controls=payload.create_controls,
            persist_report=payload.persist_report,
        )
    except AuditAutomationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AutomationRunOut.model_validate(result)


@router.get("/engagements/{engagement_id}/working-papers/export")
async def export_working_papers(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> Response:
    try:
        pack = await build_automation_pack(
            session,
            tenant_id=auth.tenant_id,
            engagement_id=_parse_engagement_id(engagement_id),
        )
    except AuditAutomationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    html = render_working_paper_html(pack)
    return Response(
        content=html,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="working-papers-{engagement_id}.html"'},
    )


@router.post("/engagements/{engagement_id}/sampling-plan")
async def create_sampling_plan(
    engagement_id: str,
    payload: SamplingRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> dict[str, Any]:
    engagement = await _load_engagement(session, _parse_engagement_id(engagement_id), auth.tenant_id)
    transactions = await _engagement_transactions(session, engagement)
    plan = build_sampling_plan(transactions, sample_size=max(1, min(payload.sample_size, 500)))
    await append_audit_event(
        session,
        tenant_id=engagement.tenant_id,
        engagement_id=engagement.id,
        jurisdiction=engagement.jurisdiction,
        event_type="SAMPLING_PLAN_GENERATED",
        entity_type="engagement",
        entity_id=str(engagement.id),
        payload={"sample_size": plan["sample_size"], "method": plan["method"], "actor": auth.client_name},
    )
    await session.commit()
    return plan


@router.post("/engagements/{engagement_id}/agents/run")
async def run_ai_audit_agents(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> dict[str, Any]:
    engagement = await _load_engagement(session, _parse_engagement_id(engagement_id), auth.tenant_id)
    transactions = await _engagement_transactions(session, engagement)
    pack = build_agent_run_pack(transactions)
    await append_audit_event(
        session,
        tenant_id=engagement.tenant_id,
        engagement_id=engagement.id,
        jurisdiction=engagement.jurisdiction,
        event_type="AI_AUDIT_AGENTS_RUN",
        entity_type="engagement",
        entity_id=str(engagement.id),
        payload={"agent_count": len(pack["agents"]), "human_review_required": True, "actor": auth.client_name},
    )
    await session.commit()
    return pack


@router.post("/engagements/{engagement_id}/confirmations", status_code=status.HTTP_201_CREATED)
async def create_confirmation_request(
    engagement_id: str,
    payload: ConfirmationRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> dict[str, Any]:
    engagement = await _load_engagement(session, _parse_engagement_id(engagement_id), auth.tenant_id)
    confirmation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"arkashri:confirmation:{engagement.id}:{payload.counterparty}:{payload.confirmation_type}:{payload.amount}:{payload.due_date}"))
    body = payload.model_dump()
    body.update({"confirmation_id": confirmation_id, "status": "REQUESTED", "actor": auth.client_name})
    await append_audit_event(
        session,
        tenant_id=engagement.tenant_id,
        engagement_id=engagement.id,
        jurisdiction=engagement.jurisdiction,
        event_type="CONFIRMATION_REQUEST_CREATED",
        entity_type="confirmation",
        entity_id=confirmation_id,
        payload=body,
    )
    await session.commit()
    return body


@router.post("/engagements/{engagement_id}/management-responses", status_code=status.HTTP_201_CREATED)
async def record_management_response(
    engagement_id: str,
    payload: ManagementResponseRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> dict[str, Any]:
    engagement = await _load_engagement(session, _parse_engagement_id(engagement_id), auth.tenant_id)
    response_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"arkashri:management-response:{engagement.id}:{payload.finding_code}:{payload.owner}"))
    body = payload.model_dump()
    body.update({"response_id": response_id, "recorded_by": auth.client_name, "human_review_required": True})
    await append_audit_event(
        session,
        tenant_id=engagement.tenant_id,
        engagement_id=engagement.id,
        jurisdiction=engagement.jurisdiction,
        event_type="MANAGEMENT_RESPONSE_RECORDED",
        entity_type="management_response",
        entity_id=response_id,
        payload=body,
    )
    await session.commit()
    return body
