from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    RegulatoryIngestRunOut,
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
    return RegulatorySourceBootstrapResponse(inserted=added, existing=total)


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
    source = await session.scalar(select(RegulatorySource).where(RegulatorySource.source_key == source_key))
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    run = await ingest_source(session, source=source)
    return RegulatorySyncResponse(runs=[RegulatoryIngestRunOut.model_validate(run)])


@router.post("/sync/jurisdiction/{jurisdiction}", response_model=list[RegulatorySyncResponse])
async def sync_jurisdiction(
    jurisdiction: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> list[RegulatorySyncResponse]:
    runs = await ingest_jurisdiction_sources(session, jurisdiction=jurisdiction)
    return [RegulatorySyncResponse(runs=[RegulatoryIngestRunOut.model_validate(r) for r in runs])]


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
    try:
        doc = await session.scalar(select(RegulatoryDocument).where(RegulatoryDocument.id == document_id))
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        knowledge_doc_id = await promote_regulatory_document(session, regulatory_document=doc)
        return RegulatoryPromoteResponse(
            regulatory_document_id=doc.id,
            knowledge_document_id=knowledge_doc_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Gap 7: Regulatory Updates Inbox ──────────────────────────────────────────

@router.get("/updates", summary="Regulatory updates inbox (ICAI / SEBI / MCA)")
async def list_regulatory_updates(
    authority: str | None = Query(default=None, description="Filter by ICAI, SEBI, or MCA"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> list[dict]:
    """
    Regulatory inbox — most recent ICAI SA circulars, SEBI circulars, MCA amendments.
    Use ?authority=ICAI|SEBI|MCA to filter by source.
    New items appear after the daily feed job runs (or POST /updates/run-now).
    """
    stmt = select(RegulatoryDocument).order_by(RegulatoryDocument.ingested_at.desc()).limit(limit)
    if authority:
        stmt = select(RegulatoryDocument).where(
            RegulatoryDocument.authority == authority.upper()
        ).order_by(RegulatoryDocument.ingested_at.desc()).limit(limit)

    docs = list(await session.scalars(stmt))
    return [
        {
            "id": doc.id,
            "authority": doc.authority,
            "jurisdiction": doc.jurisdiction,
            "title": doc.title,
            "summary": doc.summary,
            "url": doc.document_url,
            "published_on": doc.published_on.isoformat() if doc.published_on else None,
            "ingested_at": doc.ingested_at.isoformat(),
            "is_promoted": doc.is_promoted,
            "content_hash": doc.content_hash,
        }
        for doc in docs
    ]


@router.post("/updates/run-now", summary="Trigger immediate regulatory feed refresh (ICAI + SEBI + MCA)")
async def run_regulatory_feeds_now(
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
) -> dict:
    """
    Immediately fetches all three regulatory feeds and inserts any new documents.
    Returns count of new items per source. Use this to seed the inbox or for manual refresh.
    """
    from arkashri.services.regulatory_feed import run_all_feeds
    results = await run_all_feeds(session)
    total_new = sum(v for v in results.values() if v >= 0)
    return {
        "status": "completed",
        "new_items_by_source": results,
        "total_new": total_new,
    }
