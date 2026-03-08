from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.db import get_session
from arkashri.models import ClientRole, RegulatorySource, RegulatoryDocument
from arkashri.schemas import (
    RegulatorySourceBootstrapResponse,
    RegulatorySourceOut,
    RegulatorySyncResponse,
    RegulatoryDocumentOut,
    RegulatoryPromoteRequest,
    RegulatoryPromoteResponse,
)
from arkashri.services.regulatory_ingestion import (
    bootstrap_regulatory_sources,
    ingest_jurisdiction_sources,
    ingest_source,
    promote_regulatory_document,
)
from arkashri.dependencies import require_api_client, AuthContext

router = APIRouter()

@router.post("/sources/bootstrap", response_model=RegulatorySourceBootstrapResponse, status_code=status.HTTP_201_CREATED)
async def regulatory_bootstrap_sources(
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
) -> RegulatorySourceBootstrapResponse:
    added, total = await bootstrap_regulatory_sources(session)
    return RegulatorySourceBootstrapResponse(sources_added=added, total_active_sources=total)


@router.get("/sources/{jurisdiction}", response_model=list[RegulatorySourceOut])
async def list_regulatory_sources(
    jurisdiction: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> list[RegulatorySource]:
    stmt = select(RegulatorySource).where(RegulatorySource.jurisdiction == jurisdiction, RegulatorySource.is_active.is_(True))
    return list(await session.scalars(stmt))


@router.post("/sync/source/{source_key}", response_model=RegulatorySyncResponse)
async def sync_specific_source(
    source_key: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> RegulatorySyncResponse:
    from fastapi import HTTPException
    source = await session.scalar(select(RegulatorySource).where(RegulatorySource.source_key == source_key))
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
        
    run = await ingest_source(session, source=source)
    return RegulatorySyncResponse(run_id=run.id, status=run.status, fetched_count=run.fetched_count, inserted_count=run.inserted_count)


@router.post("/sync/jurisdiction/{jurisdiction}", response_model=list[RegulatorySyncResponse])
async def sync_jurisdiction(
    jurisdiction: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> list[RegulatorySyncResponse]:
    runs = await ingest_jurisdiction_sources(session, jurisdiction=jurisdiction)
    return [
        RegulatorySyncResponse(run_id=r.id, status=r.status, fetched_count=r.fetched_count, inserted_count=r.inserted_count)
        for r in runs
    ]


@router.get("/documents/{jurisdiction}", response_model=list[RegulatoryDocumentOut])
async def list_regulatory_documents(
    jurisdiction: str,
    is_promoted: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> list[RegulatoryDocument]:
    stmt = select(RegulatoryDocument).where(RegulatoryDocument.jurisdiction == jurisdiction)
    if is_promoted is not None:
        stmt = stmt.where(RegulatoryDocument.is_promoted == is_promoted)
    stmt = stmt.order_by(RegulatoryDocument.ingested_at.desc()).limit(limit)
    return list(await session.scalars(stmt))


@router.post("/documents/{document_id}/promote", response_model=RegulatoryPromoteResponse)
async def promote_document(
    document_id: int,
    payload: RegulatoryPromoteRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.REVIEWER})),
) -> RegulatoryPromoteResponse:
    from fastapi import HTTPException
    try:
        doc = await session.scalar(select(RegulatoryDocument).where(RegulatoryDocument.id == document_id))
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        knowledge_doc_id = await promote_regulatory_document(session, regulatory_document=doc)
        return RegulatoryPromoteResponse(
            document_id=doc.id,
            is_promoted=doc.is_promoted,
            promoted_knowledge_doc_id=knowledge_doc_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
