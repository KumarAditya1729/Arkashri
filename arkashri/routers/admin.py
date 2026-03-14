# pyre-ignore-all-errors

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from arkashri.db import get_session
from arkashri.models import ChainAnchor, ClientRole
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
    Displays all blockchain anchors across all tenants.
    """
    stmt = (
        select(ChainAnchor)
        .options(joinedload(ChainAnchor.attestations))
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
    Retrieves the system-wide audit trail for compliance review.
    """
    from arkashri.models import SystemAuditLog
    stmt = select(SystemAuditLog).order_by(SystemAuditLog.created_at.desc()).limit(limit).offset(offset)
    if action:
        stmt = stmt.where(SystemAuditLog.action == action)
    if tenant_id:
        stmt = stmt.where(SystemAuditLog.tenant_id == tenant_id)
        
    result = await session.execute(stmt)
    return result.scalars().all()

@router.post("/admin/engagements/{engagement_id}/export-pdf")
async def export_audit_pdf(
    engagement_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
):
    """
    Generates and returns a regulatory PDF report for an engagement.
    """
    file_path = await generate_regulatory_pdf(db, engagement_id)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="PDF generation failed.")
        
    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
        media_type="application/pdf"
    )
