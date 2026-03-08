"""
Evidence router — real multipart file upload to LocalStorageBackend,
with a DB record table for auditability.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, String, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import Base, get_session
from arkashri.models import ClientRole, Engagement
from arkashri.dependencies import require_api_client, AuthContext
from arkashri.services.evidence import evidence_service

router = APIRouter()

# ─── Model ───────────────────────────────────────────────────────────────────

class EvidenceRecord(Base):
    __tablename__ = "evidence_records"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id     = Column(String, nullable=False, index=True)
    evd_ref       = Column(String, nullable=False)           # EVD-001 etc
    file_name     = Column(String, nullable=False)
    file_path     = Column(String, nullable=False)
    file_size_kb  = Column(String, nullable=True)
    evidence_type = Column(String, nullable=False, default="Document")   # Document/Screenshot/etc
    test_ref      = Column(String, nullable=True)
    uploaded_by   = Column(String, nullable=False, default="System")
    ev_status     = Column(String, nullable=False, default="Pending Review")
    uploaded_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ─── Schemas ─────────────────────────────────────────────────────────────────

class EvidenceOut(BaseModel):
    model_config = {"from_attributes": True}
    id:            str
    engagement_id: str
    evd_ref:       str
    file_name:     str
    file_path:     str
    file_size_kb:  str | None
    evidence_type: str
    test_ref:      str | None
    uploaded_by:   str
    ev_status:     str
    uploaded_at:   datetime


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/engagements/{engagement_id}/evidence", response_model=list[EvidenceOut])
async def list_evidence(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> list[EvidenceRecord]:
    stmt = select(EvidenceRecord).where(EvidenceRecord.engagement_id == engagement_id).order_by(EvidenceRecord.uploaded_at.desc())
    return list(await session.scalars(stmt))


@router.post("/engagements/{engagement_id}/evidence", response_model=EvidenceOut, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    engagement_id: str,
    file: UploadFile = File(...),
    test_ref: str | None = None,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> EvidenceRecord:
    engagement = await session.get(Engagement, engagement_id)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Count existing for ref numbering
    count = len(list(await session.scalars(
        select(EvidenceRecord).where(EvidenceRecord.engagement_id == engagement_id)
    )))

    # Save file to disk via LocalStorageBackend
    file_path = await evidence_service.upload_evidence(engagement.tenant_id, file)
    size_kb   = f"{(file.size or 0) // 1024} KB" if file.size else None

    # Determine type from extension
    fname = file.filename or ""
    if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
        ev_type = "Screenshot"
    elif fname.lower().endswith(('.xlsx', '.xls', '.csv')):
        ev_type = "Workpaper"
    else:
        ev_type = "Document"

    record = EvidenceRecord(
        engagement_id = engagement_id,
        tenant_id     = engagement.tenant_id,
        evd_ref       = f"EVD-{count + 1:03d}",
        file_name     = fname,
        file_path     = file_path,
        file_size_kb  = size_kb,
        evidence_type = ev_type,
        test_ref      = test_ref,
        uploaded_by   = auth.client_name,
        ev_status     = "Pending Review",
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@router.delete("/engagements/{engagement_id}/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evidence(
    engagement_id: str,
    evidence_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> None:
    record = await session.get(EvidenceRecord, evidence_id)
    if not record or record.engagement_id != engagement_id:
        raise HTTPException(status_code=404, detail="Evidence not found")
    await session.delete(record)
    await session.commit()
