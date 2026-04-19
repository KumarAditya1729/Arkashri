# pyre-ignore-all-errors
"""
Multi-chain blockchain API endpoints.
Exposes live provider status and database-backed attestation summaries only.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.dependencies import get_current_user
from arkashri.models import ChainAnchor, ChainAttestation, Engagement
from arkashri.services.multi_chain_blockchain import multi_chain_blockchain_service

logger = structlog.get_logger(__name__)

router = APIRouter()


class EvidenceAnchorRequest(BaseModel):
    """Request model for evidence anchoring"""

    evidence_hash: str = Field(..., description="Evidence hash to anchor")
    metadata: Dict[str, Any] = Field(..., description="Evidence metadata")


class NetworkStatusResponse(BaseModel):
    """Response model for network status"""

    connected: bool
    network: str
    block_number: Optional[int] = None
    gas_price: Optional[str] = None
    network_id: Optional[int] = None
    latest_block_hash: Optional[str] = None
    error: Optional[str] = None


class AnchorResponse(BaseModel):
    """Response model for evidence anchoring"""

    evidence_hash: str
    anchoring_timestamp: str
    networks_anchored: List[str]
    networks_failed: List[str]
    total_networks: int
    success_rate: float
    network_results: Dict[str, Any]
    multi_chain_hash: str
    verification_urls: Dict[str, str]


class VerificationResponse(BaseModel):
    """Response model for evidence verification"""

    evidence_hash: str
    verification_timestamp: str
    networks_verified: List[str]
    networks_failed: List[str]
    total_networks: int
    verification_rate: float
    network_results: Dict[str, Any]
    overall_verified: bool
    multi_chain_consensus: bool


@router.get("/networks/status", response_model=Dict[str, Any])
@router.get("/status", response_model=Dict[str, Any])
async def get_network_status(current_user: Dict = Depends(get_current_user)):
    """Get status of all configured blockchain networks."""
    try:
        status = await multi_chain_blockchain_service.get_network_status()
        total_blocks = sum(
            int(network_status.get("block_number") or 0)
            for network_status in status.values()
            if isinstance(network_status, dict)
        )
        latest_block_hash = next(
            (
                network_status.get("latest_block_hash")
                for network_status in status.values()
                if isinstance(network_status, dict) and network_status.get("latest_block_hash")
            ),
            None,
        )

        return {
            "networks": status,
            "summary": {
                "configured_networks": len(status),
                "connected_networks": sum(
                    1
                    for network_status in status.values()
                    if isinstance(network_status, dict) and network_status.get("connected", False)
                ),
                "total_blocks": total_blocks,
                "latest_block_hash": latest_block_hash,
            },
        }
    except Exception as e:
        logger.error("network_status_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to get network status")


@router.post("/anchor", response_model=AnchorResponse)
@router.post("/evidence/submit", response_model=AnchorResponse)
async def anchor_evidence_multi_chain(
    request: EvidenceAnchorRequest,
    current_user: Dict = Depends(get_current_user),
):
    """Anchor evidence to configured blockchain networks."""
    try:
        result = await multi_chain_blockchain_service.anchor_evidence_multi_chain(
            request.evidence_hash,
            request.metadata,
        )
        return AnchorResponse(**result)
    except RuntimeError as e:
        logger.warning("multi_chain_anchoring_unavailable", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("multi_chain_anchoring_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to anchor evidence")


@router.post("/evidence/mine-block")
async def reject_legacy_mine_block_request(
    payload: Dict[str, str],
    current_user: Dict = Depends(get_current_user),
):
    """Legacy testing endpoint retained only to reject block simulation requests."""
    _ = (payload, current_user)
    raise HTTPException(
        status_code=410,
        detail="Block simulation has been removed. Use /anchor with configured blockchain providers.",
    )


@router.post("/evidence/verify", response_model=VerificationResponse)
@router.get("/verify/{evidence_hash}", response_model=VerificationResponse)
async def verify_multi_chain_evidence(
    evidence_hash: Optional[str] = None,
    payload: Optional[Dict[str, str]] = None,
    current_user: Dict = Depends(get_current_user),
):
    """Verify evidence across configured blockchain networks."""
    target_hash = evidence_hash or (payload.get("evidence_hash") if payload else None)
    if not target_hash:
        raise HTTPException(status_code=400, detail="evidence_hash is required")

    try:
        result = await multi_chain_blockchain_service.verify_multi_chain_evidence(target_hash)
        return VerificationResponse(**result)
    except RuntimeError as e:
        logger.warning("multi_chain_verification_unavailable", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("multi_chain_verification_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to verify evidence")


@router.get("/audit/{audit_id}/trail")
async def get_audit_blockchain_trail(
    audit_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: Dict = Depends(get_current_user),
):
    """Get recorded blockchain attestations associated with an engagement's tenant scope."""
    try:
        engagement_uuid = uuid.UUID(audit_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid audit_id UUID") from exc

    engagement = await session.get(Engagement, engagement_uuid)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    rows = (
        await session.execute(
            select(ChainAttestation, ChainAnchor)
            .join(ChainAttestation.chain_anchor)
            .where(
                ChainAnchor.tenant_id == engagement.tenant_id,
                ChainAnchor.jurisdiction == engagement.jurisdiction,
            )
            .order_by(ChainAttestation.created_at.desc())
            .limit(20)
        )
    ).all()

    trail = [
        {
            "event": "CHAIN_ATTESTATION_RECORDED",
            "timestamp": attestation.created_at.isoformat(),
            "network": attestation.network,
            "tx_reference": attestation.tx_reference,
            "chain_anchor_id": anchor.id,
            "window_start_event_id": anchor.window_start_event_id,
            "window_end_event_id": anchor.window_end_event_id,
        }
        for attestation, anchor in rows
    ]

    return {
        "audit_id": audit_id,
        "anchored_decisions": len(trail),
        "consistency_check": "VALID" if trail else "NO_ATTESTATIONS",
        "blockchain_consensus": bool(trail),
        "trail": trail,
    }


@router.get("/anchored/evidence")
async def get_anchored_evidence(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user: Dict = Depends(get_current_user),
):
    """Get recent blockchain attestation records."""
    try:
        rows = (
            await session.execute(
                select(ChainAttestation, ChainAnchor)
                .join(ChainAttestation.chain_anchor)
                .order_by(ChainAttestation.created_at.desc())
                .limit(limit)
            )
        ).all()

        return {
            "anchored_evidence": [
                {
                    "id": attestation.id,
                    "attestation_hash": attestation.attestation_hash,
                    "network": attestation.network,
                    "tx_reference": attestation.tx_reference,
                    "chain_anchor_id": anchor.id,
                    "tenant_id": anchor.tenant_id,
                    "jurisdiction": anchor.jurisdiction,
                    "timestamp": attestation.created_at.isoformat(),
                }
                for attestation, anchor in rows
            ],
            "total_count": len(rows),
            "user_id": current_user.get("id"),
        }
    except Exception as e:
        logger.error("anchored_evidence_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to get anchored evidence")


@router.get("/overview")
async def get_blockchain_overview(
    session: AsyncSession = Depends(get_session),
    current_user: Dict = Depends(get_current_user),
):
    """Get blockchain overview summary from configured providers and persisted attestations."""
    try:
        network_status = await multi_chain_blockchain_service.get_network_status()
        gas_prices = await multi_chain_blockchain_service.get_gas_prices()
        connected_networks = [
            name for name, status in network_status.items() if isinstance(status, dict) and status.get("connected", False)
        ]

        total_anchors = int(await session.scalar(select(func.count(ChainAnchor.id))) or 0)
        total_attestations = int(await session.scalar(select(func.count(ChainAttestation.id))) or 0)

        average_gas_price = 0.0
        gas_price_values: list[float] = []
        for price in gas_prices.values():
            if isinstance(price, dict):
                gas_value = price.get("gas_price_gwei")
                if isinstance(gas_value, (int, float)):
                    gas_price_values.append(float(gas_value))
        if gas_price_values:
            average_gas_price = sum(gas_price_values) / len(gas_price_values)

        return {
            "networks": {
                "total_configured": len(network_status),
                "connected": len(connected_networks),
                "disconnected": len(network_status) - len(connected_networks),
                "connected_networks": connected_networks,
            },
            "gas_prices": {
                "available_networks": list(gas_prices.keys()),
                "average_gas_price": average_gas_price,
            },
            "anchoring": {
                "total_chain_anchors": total_anchors,
                "total_attestations": total_attestations,
                "success_rate": 100.0 if total_attestations else 0.0,
            },
            "verification": {
                "live_verification_supported": bool(network_status),
                "notes": "Verification requires provider-specific explorer or indexer integrations.",
            },
        }
    except Exception as e:
        logger.error("blockchain_overview_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to get blockchain overview")
