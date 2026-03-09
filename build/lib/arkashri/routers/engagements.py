from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.models import ClientRole
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
from arkashri.services.engagement import create_engagement, get_engagement, compute_materiality, list_engagements
from arkashri.dependencies import require_api_client, AuthContext
from typing import List

router = APIRouter()

@router.get("/engagements", response_model=List[EngagementOut])
async def get_all_engagements(
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.READ_ONLY, ClientRole.REVIEWER})),
) -> List[EngagementOut]:
    return await list_engagements(session)

@router.post("/engagements", response_model=EngagementOut, status_code=status.HTTP_201_CREATED)
async def create_new_engagement(
    payload: EngagementCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> EngagementOut:
    return await create_engagement(session, payload)


@router.get("/engagements/{engagement_id}", response_model=EngagementOut)
async def get_engagement_by_id(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.READ_ONLY, ClientRole.REVIEWER})),
) -> EngagementOut:
    engagement = await get_engagement(session, engagement_id)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return engagement


@router.post("/engagements/{engagement_id}/materiality", response_model=MaterialityOut, status_code=status.HTTP_201_CREATED)
async def generate_materiality(
    engagement_id: uuid.UUID,
    payload: MaterialityCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> MaterialityOut:
    engagement = await get_engagement(session, engagement_id)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
        
    return await compute_materiality(
        session,
        engagement_id=engagement_id,
        tenant_id=engagement.tenant_id,
        jurisdiction=engagement.jurisdiction,
        payload=payload
    )


@router.post("/engagements/{engagement_id}/opinion", response_model=OpinionOut, status_code=status.HTTP_201_CREATED)
async def generate_opinion(
    engagement_id: uuid.UUID,
    payload: OpinionCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> OpinionOut:
    engagement = await get_engagement(session, engagement_id)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
        
    return await generate_draft_opinion(
        session,
        engagement_id=engagement_id,
        tenant_id=engagement.tenant_id,
        jurisdiction=engagement.jurisdiction,
        payload=payload
    )

@router.post("/engagements/{engagement_id}/seal", status_code=status.HTTP_201_CREATED)
async def seal_engagement(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> dict:
    """
    Generates the WORM Sealed Audit File (Arkashri_Engagement_Seal) for regulatory submission.
    """
    try:
        seal_bundle = await generate_audit_seal(session, engagement_id)
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
    engagement_id: uuid.UUID,
    payload: ESGMetricsCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ESGMetricsOut:
    """Ingest or update Environmental, Social & Governance (ESG) metrics for a given engagement."""
    engagement = await get_engagement(session, engagement_id)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    record = await upsert_esg_metrics(
        session,
        engagement_id=engagement_id,
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
    engagement_id: uuid.UUID,
    payload: ForensicProfileCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ForensicProfileOut:
    """Ingest or update the Forensic Risk Profile (Benford's law, offshore routing, sanctions probabilities) for a given engagement."""
    engagement = await get_engagement(session, engagement_id)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    record = await upsert_forensic_profile(
        session,
        engagement_id=engagement_id,
        tenant_id=engagement.tenant_id,
        payload=payload,
    )
    return ForensicProfileOut.model_validate(record)
