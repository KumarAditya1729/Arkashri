# pyre-ignore-all-errors
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from arkashri.db import get_session
import uuid

from arkashri.models import ChainAnchor, ClientRole, Engagement
from arkashri.schemas import ChainAnchorOut, ChainAttestationOut
from arkashri.dependencies import require_api_client, AuthContext
from arkashri.schemas import SystemAuditLogOut
from arkashri.services.audit_export import generate_regulatory_pdf
from fastapi.responses import FileResponse
import os

router = APIRouter()

class EvidenceLedgerEntry(ChainAnchorOut):
    attestations: list[ChainAttestationOut]

@router.get("/admin/evidence-ledger", response_model=list[EvidenceLedgerEntry])
async def get_evidence_ledger(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
):
    """
    Global evidence ledger for administrators.
    Displays blockchain anchors for the authenticated tenant.
    """
    stmt = (
        select(ChainAnchor)
        .options(joinedload(ChainAnchor.attestations))
        .where(ChainAnchor.tenant_id == _auth.tenant_id)
        .order_by(ChainAnchor.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    anchors = result.unique().scalars().all()
    return anchors

@router.get("/admin/audit-logs", response_model=list[SystemAuditLogOut])
async def get_system_audit_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    action: str | None = None,
    tenant_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
):
    """
    Retrieves the tenant audit trail for compliance review.
    """
    from arkashri.models import SystemAuditLog
    if tenant_id and tenant_id != _auth.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot read audit logs for another tenant.")
    effective_tenant = tenant_id or _auth.tenant_id
    stmt = (
        select(SystemAuditLog)
        .where(SystemAuditLog.tenant_id == effective_tenant)
        .order_by(SystemAuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if action:
        stmt = stmt.where(SystemAuditLog.action == action)
        
    result = await session.execute(stmt)
    return result.scalars().all()

@router.post("/admin/engagements/{engagement_id}/export-pdf")
async def export_audit_pdf(
    engagement_id: str,
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
):
    """
    Generates and returns a regulatory PDF report for an engagement.
    """
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID") from exc
    engagement = await db.scalar(
        select(Engagement).where(
            Engagement.id == eid,
            Engagement.tenant_id == _auth.tenant_id,
        )
    )
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found")

    file_path = await generate_regulatory_pdf(db, eid, tenant_id=_auth.tenant_id)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="PDF generation failed.")
        
    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
        media_type="application/pdf"
    )
