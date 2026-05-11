from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.dependencies import AuthContext, require_api_client
from arkashri.models import ClientRole, Engagement
from arkashri.services.specialist_audit_engine import (
    SpecialistAuditError,
    build_specialist_workprogram,
    get_specialist_engine_catalog,
    record_specialist_workprogram,
)

router = APIRouter(prefix="/specialist-audits", tags=["Specialist Audit Execution Engine"])


class SpecialistRunRequest(BaseModel):
    audit_type: str
    context: dict[str, Any] = {}


async def _load_engagement(session: AsyncSession, engagement_id: str, tenant_id: str) -> Engagement:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID") from exc
    engagement = await session.scalar(select(Engagement).where(Engagement.id == eid, Engagement.tenant_id == tenant_id))
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return engagement


@router.get("/catalog")
async def specialist_catalog(
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> dict[str, Any]:
    return get_specialist_engine_catalog()


@router.get("/{audit_type}/workprogram")
async def specialist_workprogram_preview(
    audit_type: str,
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> dict[str, Any]:
    try:
        return build_specialist_workprogram(audit_type)
    except SpecialistAuditError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/engagements/{engagement_id}/run",
    status_code=status.HTTP_201_CREATED,
)
async def run_specialist_workprogram(
    engagement_id: str,
    payload: SpecialistRunRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> dict[str, Any]:
    engagement = await _load_engagement(session, engagement_id, auth.tenant_id)
    try:
        return await record_specialist_workprogram(
            session,
            engagement=engagement,
            actor=auth.client_name,
            audit_type=payload.audit_type,
            context=payload.context,
        )
    except SpecialistAuditError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
