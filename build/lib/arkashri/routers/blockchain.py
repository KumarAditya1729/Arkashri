from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from arkashri.db import get_session
from arkashri.models import ClientRole, ChainAttestation
from arkashri.schemas import (
    BlockchainAdapterOut,
    BlockchainAnchorRequest,
    ChainAnchorOut,
    ChainAttestationOut,
)
from arkashri.services.blockchain_adapter import list_adapters, run_adapter_anchor
from arkashri.dependencies import require_api_client, AuthContext

router = APIRouter()

@router.get("/adapters", response_model=list[BlockchainAdapterOut])
def blockchain_adapters() -> list[BlockchainAdapterOut]:
    return list_adapters()


@router.post("/anchor/{tenant_id}/{jurisdiction}", response_model=ChainAnchorOut, status_code=status.HTTP_201_CREATED)
def blockchain_anchor(
    tenant_id: str,
    jurisdiction: str,
    payload: BlockchainAnchorRequest,
    session: Session = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ChainAnchorOut:
    try:
        anchor = run_adapter_anchor(
            session,
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            adapter_key=payload.adapter_key,
        )
        return ChainAnchorOut.model_validate(anchor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/attestations/{tenant_id}/{jurisdiction}", response_model=list[ChainAttestationOut])
def list_chain_attestations(
    tenant_id: str,
    jurisdiction: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> list[ChainAttestation]:
    stmt = (
        select(ChainAttestation)
        .join(ChainAttestation.chain_anchor)
        .where(
            ChainAttestation.chain_anchor.has(tenant_id=tenant_id, jurisdiction=jurisdiction)
        )
        .order_by(ChainAttestation.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))
