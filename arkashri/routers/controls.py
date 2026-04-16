# pyre-ignore-all-errors
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.models import ClientRole, Engagement, ControlEntry, ControlStatus, ControlType
from arkashri.dependencies import require_api_client, AuthContext

router = APIRouter()

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
    id: str
    engagement_id: str
    risk_id: str | None
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
    stmt = select(ControlEntry).where(ControlEntry.engagement_id == engagement_id)
    return [ControlOut.model_validate(x) for x in await session.scalars(stmt)]


@router.post("/engagements/{engagement_id}/controls", response_model=ControlOut, status_code=status.HTTP_201_CREATED)
async def create_control(
    engagement_id: str,
    payload: ControlCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ControlOut:
    # Verify engagement exists
    engagement = await session.get(Engagement, engagement_id)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    entry = ControlEntry(
        engagement_id = engagement_id,
        risk_id       = uuid.UUID(payload.risk_id) if payload.risk_id else None,
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
    entry = await session.get(ControlEntry, control_id)
    if not entry or str(entry.engagement_id) != engagement_id:
        raise HTTPException(status_code=404, detail="Control not found")
    
    entry.status = payload.status
    if payload.status == ControlStatus.EFFECTIVE:
        entry.last_tested = datetime.now(timezone.utc)
    
    await session.commit()
    await session.refresh(entry)
    return ControlOut.model_validate(entry)
