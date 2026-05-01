# pyre-ignore-all-errors
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.models import ClientRole, Engagement, ControlEntry, ControlStatus, ControlType, RiskEntry
from arkashri.dependencies import require_api_client, AuthContext

router = APIRouter()


async def _get_tenant_engagement_or_404(
    session: AsyncSession,
    engagement_id: uuid.UUID,
    auth: AuthContext,
) -> Engagement:
    engagement = await session.get(Engagement, engagement_id)
    if not engagement or engagement.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return engagement

# ─── Schemas ─────────────────────────────────────────────────────────────────

class ControlCreate(BaseModel):
    title: str
    area: str
    control_type: ControlType
    frequency: str | None = None
    owner: str | None = None
    risk_id: str | None = None

class ControlOut(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    engagement_id: uuid.UUID
    risk_id: uuid.UUID | None
    title: str
    area: str
    control_type: ControlType
    frequency: str | None
    owner: str | None
    status: ControlStatus
    last_tested: datetime | None

class ControlStatusUpdate(BaseModel):
    status: ControlStatus

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/engagements/{engagement_id}/controls", response_model=list[ControlOut])
async def list_controls(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> list[ControlOut]:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")
    await _get_tenant_engagement_or_404(session, eid, _auth)
    stmt = select(ControlEntry).where(ControlEntry.engagement_id == eid)
    return [ControlOut.model_validate(x) for x in await session.scalars(stmt)]


@router.post("/engagements/{engagement_id}/controls", response_model=ControlOut, status_code=status.HTTP_201_CREATED)
async def create_control(
    engagement_id: str,
    payload: ControlCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ControlOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")
    await _get_tenant_engagement_or_404(session, eid, _auth)
    risk_id = None
    if payload.risk_id:
        try:
            risk_id = uuid.UUID(payload.risk_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid risk_id UUID")
        risk = await session.get(RiskEntry, risk_id)
        if not risk or risk.engagement_id != eid or risk.tenant_id != _auth.tenant_id:
            raise HTTPException(status_code=404, detail="Risk not found")

    entry = ControlEntry(
        engagement_id = eid,
        risk_id       = risk_id,
        title         = payload.title,
        area          = payload.area,
        control_type  = payload.control_type,
        frequency     = payload.frequency,
        owner         = payload.owner,
        status        = ControlStatus.NOT_TESTED,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return ControlOut.model_validate(entry)


@router.patch("/engagements/{engagement_id}/controls/{control_id}", response_model=ControlOut)
async def update_control_status(
    engagement_id: str,
    control_id: str,
    payload: ControlStatusUpdate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ControlOut:
    try:
        eid = uuid.UUID(engagement_id)
        cid = uuid.UUID(control_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")
    entry = await session.get(ControlEntry, cid)
    if not entry or entry.engagement_id != eid:
        raise HTTPException(status_code=404, detail="Control not found")
    await _get_tenant_engagement_or_404(session, eid, _auth)
    
    entry.status = payload.status
    if payload.status == ControlStatus.EFFECTIVE:
        entry.last_tested = datetime.now(timezone.utc)
    
    await session.commit()
    await session.refresh(entry)
    return ControlOut.model_validate(entry)
