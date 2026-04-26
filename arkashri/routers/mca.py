from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.dependencies import AuthContext, require_api_client
from arkashri.models import ClientRole
from arkashri.services.mca_enrichment import (
    MCAEnrichmentError,
    enrich_engagement_with_mca,
    get_engagement_mca_snapshot,
)

router = APIRouter(prefix="/mca", tags=["MCA Company Master"])


class MCAEnrichmentRequest(BaseModel):
    cin: str = Field(min_length=21, max_length=21)
    manual_master_data: dict[str, Any] | None = None


class MCASnapshotOut(BaseModel):
    engagement_id: str
    mca_company_master: dict[str, Any]


@router.post(
    "/engagements/{engagement_id}/company-master",
    response_model=MCASnapshotOut,
    status_code=status.HTTP_200_OK,
)
async def enrich_engagement_company_master(
    engagement_id: str,
    payload: MCAEnrichmentRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> MCASnapshotOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID") from None

    try:
        snapshot = await enrich_engagement_with_mca(
            session,
            engagement_id=eid,
            tenant_id=auth.tenant_id,
            cin=payload.cin,
            actor_id=auth.client_name,
            manual_master_data=payload.manual_master_data,
        )
    except MCAEnrichmentError as exc:
        detail = str(exc)
        status_code = 400
        if "not found" in detail.lower():
            status_code = 404
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return MCASnapshotOut(engagement_id=engagement_id, mca_company_master=snapshot)


@router.get(
    "/engagements/{engagement_id}/company-master",
    response_model=MCASnapshotOut,
)
async def get_engagement_company_master(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> MCASnapshotOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID") from None

    try:
        snapshot = await get_engagement_mca_snapshot(
            session,
            engagement_id=eid,
            tenant_id=auth.tenant_id,
        )
    except MCAEnrichmentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MCASnapshotOut(engagement_id=engagement_id, mca_company_master=snapshot)
