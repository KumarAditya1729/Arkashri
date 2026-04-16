# pyre-ignore-all-errors
"""
Risk Register router — engagement-scoped CRUD for audit risks.
Wires the frontend Risk Register page to Postgres.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.models import ClientRole, Engagement, RiskEntry, RiskLikelihood, RiskImpact, RiskStatus
from arkashri.dependencies import require_api_client, AuthContext

router = APIRouter()


# ─── Schemas ─────────────────────────────────────────────────────────────────

class RiskCreate(BaseModel):
    title:      str
    area:       str = "General"
    likelihood: RiskLikelihood
    impact:     RiskImpact
    owner:      str = "Unassigned"
    control_ref: str | None = None

class RiskStatusUpdate(BaseModel):
    status: RiskStatus

class RiskOut(BaseModel):
    model_config = {"from_attributes": True}
    id:          str
    engagement_id: str
    risk_ref:    str
    title:       str
    area:        str
    likelihood:  RiskLikelihood
    impact:      RiskImpact
    risk_score:  float
    owner:       str
    control_ref: str | None
    risk_status: RiskStatus
    created_at:  datetime
    updated_at:  datetime


# ─── Score helper ─────────────────────────────────────────────────────────────

_LIKELIHOOD_WEIGHT = {RiskLikelihood.HIGH: 3, RiskLikelihood.MEDIUM: 2, RiskLikelihood.LOW: 1}
_IMPACT_WEIGHT     = {RiskImpact.CRITICAL: 4, RiskImpact.HIGH: 3, RiskImpact.MEDIUM: 2, RiskImpact.LOW: 1}

def _score(likelihood: RiskLikelihood, impact: RiskImpact) -> float:
    return min(_LIKELIHOOD_WEIGHT[likelihood] * _IMPACT_WEIGHT[impact] * 8.0, 99.0)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/engagements/{engagement_id}/risks", response_model=list[RiskOut])
async def list_risks(
    engagement_id: str,
    risk_status: RiskStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> list[RiskOut]:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")
    stmt = select(RiskEntry).where(RiskEntry.engagement_id == eid)
    if risk_status:
        stmt = stmt.where(RiskEntry.risk_status == risk_status) # type: ignore
    stmt = stmt.order_by(RiskEntry.risk_score.desc())
    return [RiskOut.model_validate(x) for x in await session.scalars(stmt)]


@router.post("/engagements/{engagement_id}/risks", response_model=RiskOut, status_code=status.HTTP_201_CREATED)
async def create_risk(
    engagement_id: str,
    payload: RiskCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> RiskOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")

    # Verify engagement exists
    engagement = await session.get(Engagement, eid)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Auto-generate RSK ref
    count_stmt = select(func.count()).select_from(
        select(RiskEntry.id).where(RiskEntry.engagement_id == eid).subquery()
    )
    count = (await session.scalar(count_stmt)) or 0

    entry = RiskEntry(
        engagement_id = eid,
        tenant_id     = engagement.tenant_id,
        risk_ref      = f"RSK-{count + 1:03d}",
        title         = payload.title,
        area          = payload.area,
        likelihood    = payload.likelihood,
        impact        = payload.impact,
        risk_score    = _score(payload.likelihood, payload.impact),
        owner         = payload.owner,
        control_ref   = payload.control_ref,
        risk_status   = RiskStatus.OPEN,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return RiskOut.model_validate(entry)


@router.patch("/engagements/{engagement_id}/risks/{risk_id}", response_model=RiskOut)
async def update_risk_status(
    engagement_id: str,
    risk_id: str,
    payload: RiskStatusUpdate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> RiskOut:
    try:
        eid = uuid.UUID(engagement_id)
        rid = uuid.UUID(risk_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")
    entry = await session.get(RiskEntry, rid)
    if not entry or entry.engagement_id != eid:
        raise HTTPException(status_code=404, detail="Risk not found")
    entry.risk_status = payload.status # type: ignore
    entry.updated_at = datetime.now(timezone.utc) # type: ignore
    await session.commit()
    await session.refresh(entry)
    return RiskOut.model_validate(entry)
