# pyre-ignore-all-errors
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.models import ClientRole, Engagement
from arkashri.schemas import (
    EngagementCreate,
    EngagementOut,
    MaterialityCreate,
    MaterialityOut,
    OpinionCreate,
    OpinionOut,
    ESGMetricsCreate,
    ESGMetricsOut,
    ForensicProfileCreate,
    ForensicProfileOut,
)
from arkashri.services.engagement import create_engagement, get_engagement, compute_materiality
from arkashri.services.opinion import generate_draft_opinion
from arkashri.services.seal import generate_audit_seal
from arkashri.services.esg import upsert_esg_metrics
from arkashri.services.forensic import upsert_forensic_profile
from arkashri.dependencies import require_api_client, AuthContext

router = APIRouter()

@router.post("/engagements", response_model=EngagementOut, status_code=status.HTTP_201_CREATED)
async def create_new_engagement(
    payload: EngagementCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> EngagementOut:
    engagement = await create_engagement(session, payload)
    return EngagementOut.model_validate(engagement)


@router.get("/engagements", response_model=list[EngagementOut])
async def list_engagements(
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.READ_ONLY, ClientRole.REVIEWER})),
) -> list[EngagementOut]:
    """List all engagements ordered by most recent first."""
    results = list(await session.scalars(select(Engagement).order_by(Engagement.created_at.desc())))
    return [EngagementOut.model_validate(e) for e in results]


@router.get("/engagements/{engagement_id}", response_model=EngagementOut)
async def get_engagement_by_id(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.READ_ONLY, ClientRole.REVIEWER})),
) -> EngagementOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")
    engagement = await get_engagement(session, eid)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return EngagementOut.model_validate(engagement)


@router.post("/engagements/{engagement_id}/materiality", response_model=MaterialityOut, status_code=status.HTTP_201_CREATED)
async def generate_materiality(
    engagement_id: str,
    payload: MaterialityCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> MaterialityOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")
    engagement = await get_engagement(session, eid)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
        
    materiality = await compute_materiality(
        session,
        engagement_id=eid,
        tenant_id=engagement.tenant_id,
        jurisdiction=engagement.jurisdiction,
        payload=payload
    )
    return MaterialityOut.model_validate(materiality)


@router.post("/engagements/{engagement_id}/opinion", response_model=OpinionOut, status_code=status.HTTP_201_CREATED)
async def generate_opinion(
    engagement_id: str,
    payload: OpinionCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> OpinionOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")
    engagement = await get_engagement(session, eid)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
        
    opinion = await generate_draft_opinion(
        session,
        engagement_id=eid,
        tenant_id=engagement.tenant_id,
        jurisdiction=engagement.jurisdiction,
        payload=payload
    )
    return OpinionOut.model_validate(opinion)

@router.post("/engagements/{engagement_id}/seal", status_code=status.HTTP_201_CREATED)
async def seal_engagement(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> dict:
    """
    Generates the WORM Sealed Audit File (Arkashri_Engagement_Seal) for regulatory submission.
    """
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")
    try:
        seal_bundle = await generate_audit_seal(session, eid)
        return {"status": "success", "message": "Engagement sealed cryptographically.", "seal": seal_bundle}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/engagements/{engagement_id}/esg",
    response_model=ESGMetricsOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest ESG metrics for an engagement",
)
async def upsert_engagement_esg(
    engagement_id: str,
    payload: ESGMetricsCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ESGMetricsOut:
    """Ingest or update Environmental, Social & Governance (ESG) metrics for a given engagement."""
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")
    engagement = await get_engagement(session, eid)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    record = await upsert_esg_metrics(
        session,
        engagement_id=eid,
        tenant_id=engagement.tenant_id,
        payload=payload,
    )
    return ESGMetricsOut.model_validate(record)


@router.post(
    "/engagements/{engagement_id}/forensic",
    response_model=ForensicProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest forensic risk profile for an engagement",
)
async def upsert_engagement_forensic(
    engagement_id: str,
    payload: ForensicProfileCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ForensicProfileOut:
    """Ingest or update the Forensic Risk Profile (Benford's law, offshore routing, sanctions probabilities) for a given engagement."""
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")
    engagement = await get_engagement(session, eid)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    record = await upsert_forensic_profile(
        session,
        engagement_id=eid,
        tenant_id=engagement.tenant_id,
        payload=payload,
    )
    return ForensicProfileOut.model_validate(record)
