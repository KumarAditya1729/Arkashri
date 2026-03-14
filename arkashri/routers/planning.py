# pyre-ignore-all-errors
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.models import ClientRole, Engagement, EngagementPhase, TeamMember, PhaseStatus
from arkashri.dependencies import require_api_client, AuthContext

router = APIRouter()

# ─── Schemas ─────────────────────────────────────────────────────────────────

class PhaseCreate(BaseModel):
    name: str
    status: PhaseStatus = PhaseStatus.UPCOMING
    start_date: datetime | None = None
    end_date: datetime | None = None
    owner: str | None = None
    progress: int = 0

class PhaseOut(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    engagement_id: str
    name: str
    status: PhaseStatus
    start_date: datetime | None
    end_date: datetime | None
    owner: str | None
    progress: int

class TeamMemberCreate(BaseModel):
    name: str
    role: str
    initials: str | None = None
    color: str | None = None

class TeamMemberOut(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    engagement_id: str
    name: str
    role: str
    initials: str | None
    color: str | None

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/engagements/{engagement_id}/phases", response_model=list[PhaseOut])
async def list_phases(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> list[PhaseOut]:
    stmt = select(EngagementPhase).where(EngagementPhase.engagement_id == engagement_id)
    return [PhaseOut.model_validate(x) for x in await session.scalars(stmt)]


@router.post("/engagements/{engagement_id}/phases", response_model=PhaseOut, status_code=status.HTTP_201_CREATED)
async def create_phase(
    engagement_id: str,
    payload: PhaseCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> PhaseOut:
    entry = EngagementPhase(
        engagement_id = engagement_id,
        name          = payload.name,
        status        = payload.status,
        start_date    = payload.start_date,
        end_date      = payload.end_date,
        owner         = payload.owner,
        progress      = payload.progress
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return PhaseOut.model_validate(entry)


@router.get("/engagements/{engagement_id}/team", response_model=list[TeamMemberOut])
async def list_team(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> list[TeamMemberOut]:
    stmt = select(TeamMember).where(TeamMember.engagement_id == engagement_id)
    return [TeamMemberOut.model_validate(x) for x in await session.scalars(stmt)]


@router.post("/engagements/{engagement_id}/team", response_model=TeamMemberOut, status_code=status.HTTP_201_CREATED)
async def add_team_member(
    engagement_id: str,
    payload: TeamMemberCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> TeamMemberOut:
    entry = TeamMember(
        engagement_id = engagement_id,
        name          = payload.name,
        role          = payload.role,
        initials      = payload.initials,
        color         = payload.color
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return TeamMemberOut.model_validate(entry)
