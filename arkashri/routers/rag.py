# pyre-ignore-all-errors
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.db import get_session
from arkashri.models import ClientRole, KnowledgeDocument, KnowledgeSourceType
from arkashri.schemas import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentOut,
    RagQueryRequest,
    RagQueryResponse,
    RagSourceOut,
)
from arkashri.services.rag import create_knowledge_document, query_knowledge
from arkashri.services.evidence import evidence_service
from arkashri.dependencies import require_api_client, AuthContext

router = APIRouter()

@router.post("/documents", response_model=KnowledgeDocumentOut, status_code=status.HTTP_201_CREATED)
async def create_rag_document(
    payload: KnowledgeDocumentCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.REVIEWER})),
) -> KnowledgeDocumentOut:
    document = await create_knowledge_document(
        session,
        document_key=payload.document_key,
        jurisdiction=payload.jurisdiction,
        source_type=payload.source_type,
        title=payload.title,
        content=payload.content,
        metadata_json=payload.metadata_json,
        version=1,
        is_active=True,
    )
    return KnowledgeDocumentOut.model_validate(document)


@router.post("/upload", response_model=KnowledgeDocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_evidence_and_create_rag(
    file: UploadFile = File(...),
    document_key: str = Form(...),
    jurisdiction: str = Form(...),
    title: str = Form(...),
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.REVIEWER})),
) -> KnowledgeDocumentOut:
    evidence_url = await evidence_service.upload_evidence(tenant_id="_system", file=file)
    content_bytes = await evidence_service.get_evidence_content(evidence_url)
    try:
        content_text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content_text = f"Binary content uploaded to {evidence_url}"
        
    metadata = {
        "filename": file.filename,
        "content_type": file.content_type,
        "evidence_url": evidence_url,
    }

    document = await create_knowledge_document(
        session,
        document_key=document_key,
        jurisdiction=jurisdiction,
        source_type=KnowledgeSourceType("MANUAL_UPLOAD"),
        title=title,
        content=content_text,
        metadata_json=metadata,
        version=1,
        is_active=True,
    )
    return KnowledgeDocumentOut.model_validate(document)



@router.get("/documents/{jurisdiction}", response_model=list[KnowledgeDocumentOut])
async def list_rag_documents(
    jurisdiction: str,
    include_global: bool = Query(default=True),
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> list[KnowledgeDocumentOut]:
    jur_filter = [jurisdiction]
    if include_global and jurisdiction != "GLOBAL":
        jur_filter.append("GLOBAL")

    stmt = select(KnowledgeDocument).where(KnowledgeDocument.jurisdiction.in_(jur_filter))
    if not include_inactive:
        stmt = stmt.where(KnowledgeDocument.is_active.is_(True))
    stmt = stmt.order_by(KnowledgeDocument.created_at.desc()).limit(limit)

    return [KnowledgeDocumentOut.model_validate(d) for d in await session.scalars(stmt)]


@router.post("/query", response_model=RagQueryResponse)
async def rag_query(
    payload: RagQueryRequest,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> RagQueryResponse:
    # We pass 'tenant_id="<active>"' logic inside or let query_knowledge handle generic searches
    # Defaulting to _system if tenant is implied to be overall knowledge
    # Defaulting to _system if tenant is implied to be overall knowledge
    res_payload = await query_knowledge(
        session,
        jurisdiction=payload.jurisdiction,
        query_text=payload.query_text,
        audit_type=payload.audit_type,
        top_k=payload.top_k,
    )
    return RagQueryResponse(
        query_hash=res_payload[0],
        answer=res_payload[2] if len(res_payload) > 2 else "",
        sources=[RagSourceOut.model_validate(x) for x in res_payload[1]],
    )
