# pyre-ignore-all-errors
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.models import ChainAnchor, ChainAttestation, ClientRole
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
def blockchain_adapters() -> list[dict[str, str]]:
    return list_adapters()


@router.post("/anchor/{tenant_id}/{jurisdiction}", response_model=ChainAnchorOut, status_code=status.HTTP_201_CREATED)
async def blockchain_anchor(
    tenant_id: str,
    jurisdiction: str,
    payload: BlockchainAnchorRequest,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ChainAnchorOut:
    try:
        attestation_result = run_adapter_anchor(
            payload.adapter_key,
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            merkle_root=payload.merkle_root,
            window_start_event_id=payload.window_start_event_id,
            window_end_event_id=payload.window_end_event_id,
            chain_anchor_id=payload.chain_anchor_id,
        )

        anchor: ChainAnchor | None = None
        if payload.chain_anchor_id > 0:
            anchor = await session.get(ChainAnchor, payload.chain_anchor_id)
            if anchor is not None and (
                anchor.tenant_id != tenant_id or anchor.jurisdiction != jurisdiction
            ):
                raise HTTPException(status_code=409, detail="chain_anchor_id belongs to a different tenant scope")

        if anchor is None:
            anchor_kwargs = {
                "tenant_id": tenant_id,
                "jurisdiction": jurisdiction,
                "window_start_event_id": payload.window_start_event_id,
                "window_end_event_id": payload.window_end_event_id,
                "merkle_root": payload.merkle_root,
                "anchor_provider": payload.adapter_key,
                "external_reference": payload.external_reference or attestation_result.tx_reference,
            }
            if payload.chain_anchor_id > 0:
                anchor = ChainAnchor(id=payload.chain_anchor_id, **anchor_kwargs)
            else:
                anchor = ChainAnchor(**anchor_kwargs)
            session.add(anchor)
            await session.flush()
        else:
            anchor.window_start_event_id = payload.window_start_event_id
            anchor.window_end_event_id = payload.window_end_event_id
            anchor.merkle_root = payload.merkle_root
            anchor.anchor_provider = payload.adapter_key
            anchor.external_reference = payload.external_reference or attestation_result.tx_reference
            session.add(anchor)

        attestation = ChainAttestation(
            chain_anchor_id=anchor.id,
            adapter_key=attestation_result.adapter_key,
            network=attestation_result.network,
            tx_reference=attestation_result.tx_reference,
            attestation_hash=attestation_result.attestation_hash,
            provider_payload=attestation_result.provider_payload,
        )
        session.add(attestation)
        await session.commit()
        await session.refresh(anchor)
        return ChainAnchorOut.model_validate(anchor)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/attestations/{tenant_id}/{jurisdiction}", response_model=list[ChainAttestationOut])
async def list_chain_attestations(
    tenant_id: str,
    jurisdiction: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> list[ChainAttestationOut]:
    stmt = (
        select(ChainAttestation)
        .join(ChainAttestation.chain_anchor)
        .where(
            ChainAttestation.chain_anchor.has(tenant_id=tenant_id, jurisdiction=jurisdiction)
        )
        .order_by(ChainAttestation.created_at.desc())
        .limit(limit)
    )
    rows = await session.scalars(stmt)
    return [ChainAttestationOut.model_validate(c) for c in rows]
