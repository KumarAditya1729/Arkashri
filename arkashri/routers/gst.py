# pyre-ignore-all-errors
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.dependencies import AuthContext, require_api_client
from arkashri.models import ClientRole
from arkashri.services.gst_reconciliation import (
    GSTReconciliationError,
    get_gst_reconciliations,
    run_gst_reconciliation,
)

router = APIRouter(prefix="/gst", tags=["GST Reconciliation"])


class GSTPortalRecord(BaseModel):
    invoice_no: str | None = None
    invoice_number: str | None = None
    voucher_number: str | None = None
    document_number: str | None = None
    gstin: str | None = None
    counterparty_gstin: str | None = None
    taxable_value: float | None = None
    invoice_value: float | None = None
    tax_amount: float | None = None
    gst_amount: float | None = None
    tax_total: float | None = None
    portal_tax: float | None = None
    period: str | None = None
    tax_period: str | None = None
    filing_period: str | None = None


class GSTReconciliationRequest(BaseModel):
    portal_records: list[GSTPortalRecord] = Field(default_factory=list, min_length=1)


class GSTReconciliationOut(BaseModel):
    recon_type: str
    reconciled_at: str
    summary: dict[str, Any]
    mismatches: list[dict[str, Any]]


class GSTReconciliationListOut(BaseModel):
    reconciliations: dict[str, Any]


@router.post(
    "/engagements/{engagement_id}/reconcile/gstr1-vs-books",
    response_model=GSTReconciliationOut,
    status_code=status.HTTP_201_CREATED,
)
async def reconcile_gstr1_vs_books(
    engagement_id: str,
    payload: GSTReconciliationRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> GSTReconciliationOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")

    try:
        result = await run_gst_reconciliation(
            session,
            engagement_id=eid,
            tenant_id=auth.tenant_id,
            actor_id=auth.client_name,
            recon_type="gstr1_vs_books",
            portal_records=[record.model_dump(exclude_none=True) for record in payload.portal_records],
        )
    except GSTReconciliationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return GSTReconciliationOut(
        recon_type=result.recon_type,
        reconciled_at=result.reconciled_at,
        summary=result.summary,
        mismatches=result.mismatches,
    )


@router.post(
    "/engagements/{engagement_id}/reconcile/gstr2b-vs-itc",
    response_model=GSTReconciliationOut,
    status_code=status.HTTP_201_CREATED,
)
async def reconcile_gstr2b_vs_itc(
    engagement_id: str,
    payload: GSTReconciliationRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> GSTReconciliationOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")

    try:
        result = await run_gst_reconciliation(
            session,
            engagement_id=eid,
            tenant_id=auth.tenant_id,
            actor_id=auth.client_name,
            recon_type="gstr2b_vs_itc",
            portal_records=[record.model_dump(exclude_none=True) for record in payload.portal_records],
        )
    except GSTReconciliationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return GSTReconciliationOut(
        recon_type=result.recon_type,
        reconciled_at=result.reconciled_at,
        summary=result.summary,
        mismatches=result.mismatches,
    )


@router.get(
    "/engagements/{engagement_id}/reconciliations",
    response_model=GSTReconciliationListOut,
)
async def list_gst_reconciliations(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> GSTReconciliationListOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")

    try:
        reconciliations = await get_gst_reconciliations(
            session,
            engagement_id=eid,
            tenant_id=auth.tenant_id,
        )
    except GSTReconciliationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return GSTReconciliationListOut(reconciliations=reconciliations)
