# pyre-ignore-all-errors
"""
Evidence router — real multipart file upload to LocalStorageBackend,
with a DB record table for auditability.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status, Form
import structlog
import filetype
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.db import get_session
from arkashri.models import ClientRole, Engagement, EvidenceRecord
from arkashri.dependencies import require_api_client, AuthContext
from arkashri.services.evidence import evidence_service
from arkashri.config import get_settings

router = APIRouter()
logger = structlog.get_logger(__name__)


# ─── Model Moved to models.py ────────────────────────────────────────────────

# ─── Schemas ─────────────────────────────────────────────────────────────────


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


class LinkTransactionsRequest(BaseModel):
    transaction_ids: list[uuid.UUID]


class EvidenceDownloadUrlOut(BaseModel):
    evidence_id: str
    url: str
    expires_in: int


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/engagements/{engagement_id}/evidence", response_model=list[EvidenceOut])
async def list_evidence(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> list[EvidenceRecord]:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")
    engagement = await session.get(Engagement, eid)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    if engagement.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied: engagement belongs to a different tenant.")
    stmt = (
        select(EvidenceRecord)
        .where(EvidenceRecord.engagement_id == eid, EvidenceRecord.tenant_id == auth.tenant_id)
        .order_by(EvidenceRecord.uploaded_at.desc())
    )
    return list(await session.scalars(stmt))


@router.post("/engagements/{engagement_id}/evidence", response_model=EvidenceOut, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    engagement_id: str,
    file: UploadFile = File(...),
    test_ref: str | None = Form(None),
    transaction_ids: str | None = Form(None), # Comma-separated UUIDs
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> EvidenceRecord:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")
    engagement = await session.get(Engagement, eid)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    if engagement.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied: engagement belongs to a different tenant.")

    # M-9 FIX: sealed engagements are WORM — no mutations allowed
    from arkashri.models import EngagementStatus
    if engagement.status == EngagementStatus.SEALED:
        raise HTTPException(
            status_code=409,
            detail="Cannot upload evidence to a sealed engagement. The audit bundle is WORM-locked."
        )

    # Validate file type and size
    settings = get_settings()
    allowed_types = {item.strip() for item in settings.allowed_file_types.split(",") if item.strip()}

    # H-NEW-8: Sanitize and validate file type server-side (DO NOT trust client Content-Type)
    # Read first 2KB for sniffing
    head = await file.read(2048)
    await file.seek(0)
    
    kind = filetype.guess(head)
    if kind is None:
        # Fallback for plain text if binary sniff fails
        try:
            head.decode('utf-8')
            detected_mime = "text/plain"
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=415, 
                detail="Unsupported or malicious file type detected. Please upload valid audit evidence (PDF, Excel, Images, CSV, Text)."
            )
    else:
        detected_mime = kind.mime

    if detected_mime not in allowed_types:
        logger.warning(
            "BLOCKED_UPLOAD_MIME",
            detected=detected_mime,
            allowed=allowed_types,
            user=auth.client_name,  # C-4 FIX: was `current_user.email` (undefined)
        )
        raise HTTPException(
            status_code=415,
            detail=f"File content type '{detected_mime}' is not permitted. Allowed types: {', '.join(sorted(allowed_types))}"
        )

    file_bytes = await file.read()
    if len(file_bytes) > settings.max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"File size {len(file_bytes)} bytes exceeds maximum allowed size of {settings.max_file_size} bytes"
        )
    await file.seek(0)

    # H-8 FIX: Use MAX-based next ref instead of COUNT to avoid duplicate refs
    # under concurrent uploads. COUNT returns the same value to two racing requests;
    # MAX(evd_ref) + 1 pattern is safe when combined with DB-level uniqueness.
    from sqlalchemy import func as _func
    max_ref_result = await session.scalar(
        select(_func.max(EvidenceRecord.evd_ref)).where(EvidenceRecord.engagement_id == eid)
    )
    if max_ref_result and max_ref_result.startswith("EVD-"):
        try:
            next_num = int(max_ref_result[4:]) + 1
        except ValueError:
            next_num = 1
    else:
        next_num = 1

    # Save file to the configured evidence store
    file_path = await evidence_service.upload_evidence(engagement.tenant_id, file)
    size_kb   = f"{len(file_bytes) // 1024} KB" if file_bytes else None

    # Determine type from extension
    fname = file.filename or ""
    if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
        ev_type = "Screenshot"
    elif fname.lower().endswith(('.xlsx', '.xls', '.csv')):
        ev_type = "Workpaper"
    else:
        ev_type = "Document"

    record = EvidenceRecord(
        engagement_id = eid,
        tenant_id     = engagement.tenant_id,
        evd_ref       = f"EVD-{next_num:03d}",
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
    logger.info(
        "evidence_uploaded",
        source="FILE_UPLOAD",
        tenant_id=engagement.tenant_id,
        engagement_id=str(eid),
        evidence_id=str(record.id),
        file_name=fname,
    )

    # Auto-link transactions if provided
    if transaction_ids:
        try:
            tx_uuids = [uuid.UUID(tid.strip()) for tid in transaction_ids.split(",") if tid.strip()]
            if tx_uuids:
                await evidence_service.link_evidence_to_transactions(
                    session, record.id, tx_uuids, engagement.tenant_id, auth.client_name
                )
        except ValueError:
            logger.warning(f"Failed to parse transaction_ids in upload: {transaction_ids}")

    return record


@router.get("/engagements/{engagement_id}/evidence/{evidence_id}/download-url", response_model=EvidenceDownloadUrlOut)
async def get_evidence_download_url(
    engagement_id: str,
    evidence_id: str,
    expires_in: int = Query(default=3600, ge=60, le=86400),
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> EvidenceDownloadUrlOut:
    try:
        eid = uuid.UUID(engagement_id)
        ev_id = uuid.UUID(evidence_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")

    record = await session.get(EvidenceRecord, ev_id)
    if not record or record.engagement_id != eid or record.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Evidence not found")

    url = await evidence_service.get_evidence_download_url(record.file_path, expires_in=expires_in)
    return EvidenceDownloadUrlOut(evidence_id=evidence_id, url=url, expires_in=expires_in)


@router.post("/evidence/{evidence_id}/link-transactions", status_code=status.HTTP_201_CREATED)
async def link_evidence_to_tx(
    evidence_id: str,
    payload: LinkTransactionsRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> dict:
    """
    Manually link an existing evidence file to a set of transactions.
    """
    try:
        ev_id = uuid.UUID(evidence_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid evidence_id UUID")
    
    record = await session.get(EvidenceRecord, ev_id)
    if not record:
        raise HTTPException(status_code=404, detail="Evidence record not found")
    if record.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied: evidence belongs to a different tenant.")
        
    await evidence_service.link_evidence_to_transactions(
        session, ev_id, payload.transaction_ids, record.tenant_id, auth.client_name
    )
    
    return {"status": "success", "linked_count": len(payload.transaction_ids)}


@router.delete("/engagements/{engagement_id}/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evidence(
    engagement_id: str,
    evidence_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> None:
    try:
        eid = uuid.UUID(engagement_id)
        evd_id = uuid.UUID(evidence_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")
    record = await session.get(EvidenceRecord, evd_id)
    if not record or record.engagement_id != eid or record.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Evidence not found")

    # M-9 FIX: sealed engagements are WORM — no mutations allowed
    from arkashri.models import EngagementStatus
    eng_for_delete = await session.get(Engagement, eid)
    if eng_for_delete and eng_for_delete.status == EngagementStatus.SEALED:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete evidence from a sealed engagement. The audit bundle is WORM-locked."
        )
    await evidence_service.delete_evidence(record.file_path)
    await session.delete(record)
    await session.commit()
