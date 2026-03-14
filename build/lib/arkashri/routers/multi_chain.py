# pyre-ignore-all-errors
"""
Multi-Chain Blockchain API endpoints
Provides blockchain anchoring and verification across multiple networks
"""
from __future__ import annotations

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import structlog

from arkashri.services.multi_chain_blockchain import multi_chain_blockchain_service
from arkashri.dependencies import get_current_user

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

@router.post("/anchor", response_model=AnchorResponse)
async def anchor_evidence_multi_chain(
    request: EvidenceAnchorRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(get_current_user)
):
    """Anchor evidence to multiple blockchain networks"""
    try:
        result = await multi_chain_blockchain_service.anchor_evidence_multi_chain(
            request.evidence_hash,
            request.metadata
        )
        
        # Log anchoring event
        logger.info(
            "evidence_anchored",
            evidence_hash=request.evidence_hash,
            networks_anchored=result["networks_anchored"],
            user_id=current_user.get("id")
        )
        
        return AnchorResponse(**result)
    except Exception as e:
        logger.error("multi_chain_anchoring_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to anchor evidence")

@router.get("/verify/{evidence_hash}", response_model=VerificationResponse)
async def verify_multi_chain_evidence(
    evidence_hash: str,
    current_user: Dict = Depends(get_current_user)
):
    """Verify evidence across multiple blockchain networks"""
    try:
        result = await multi_chain_blockchain_service.verify_multi_chain_evidence(evidence_hash)
        
        # Log verification event
        logger.info(
            "evidence_verified",
            evidence_hash=evidence_hash,
            networks_verified=result["networks_verified"],
            overall_verified=result["overall_verified"],
            user_id=current_user.get("id")
        )
        
        return VerificationResponse(**result)
    except Exception as e:
        logger.error("multi_chain_verification_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to verify evidence")

@router.get("/networks/status", response_model=Dict[str, NetworkStatusResponse])
async def get_network_status(current_user: Dict = Depends(get_current_user)):
    """Get status of all blockchain networks"""
    try:
        status = await multi_chain_blockchain_service.get_network_status()
        
        # Convert to response models
        response = {}
        for network_name, network_data in status.items():
            response[network_name] = NetworkStatusResponse(**network_data)
        
        return response
    except Exception as e:
        logger.error("network_status_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to get network status")

@router.get("/gas/prices")
async def get_gas_prices(current_user: Dict = Depends(get_current_user)):
    """Get gas prices from all connected EVM networks"""
    try:
        gas_prices = await multi_chain_blockchain_service.get_gas_prices()
        
        return {
            "gas_prices": gas_prices,
            "timestamp": "2026-03-10T00:00:00Z",
            "networks_available": list(gas_prices.keys())
        }
    except Exception as e:
        logger.error("gas_prices_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to get gas prices")

@router.get("/anchored/evidence")
async def get_anchored_evidence(current_user: Dict = Depends(get_current_user)):
    """Get list of anchored evidence"""
    try:
        # Mock data - in production, fetch from database
        return {
            "anchored_evidence": [
                {
                    "id": "1",
                    "evidence_hash": "0xabc123def456...",
                    "networks_anchored": ["polkadot", "ethereum", "polygon"],
                    "timestamp": "2026-03-10T10:30:00Z",
                    "multi_chain_hash": "0x789xyz456..."
                },
                {
                    "id": "2",
                    "evidence_hash": "0xdef789ghi012...",
                    "networks_anchored": ["ethereum", "polygon"],
                    "timestamp": "2026-03-10T09:15:00Z",
                    "multi_chain_hash": "0x456uvw789..."
                }
            ],
            "total_count": 2,
            "user_id": current_user.get("id")
        }
    except Exception as e:
        logger.error("anchored_evidence_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to get anchored evidence")

@router.get("/overview")
async def get_blockchain_overview(current_user: Dict = Depends(get_current_user)):
    """Get blockchain overview summary"""
    try:
        network_status = await multi_chain_blockchain_service.get_network_status()
        gas_prices = await multi_chain_blockchain_service.get_gas_prices()
        
        connected_networks = [name for name, status in network_status.items() if status.get("connected", False)]
        
        return {
            "networks": {
                "total_configured": len(network_status),
                "connected": len(connected_networks),
                "disconnected": len(network_status) - len(connected_networks),
                "connected_networks": connected_networks
            },
            "gas_prices": {
                "available_networks": list(gas_prices.keys()),
                "average_gas_price": sum(float(price.get("gas_price", "0").replace(" Gwei", "")) for price in gas_prices.values()) / len(gas_prices) if gas_prices else 0
            },
            "anchoring": {
                "total_evidence_anchored": 2,
                "successful_anchors": 2,
                "failed_anchors": 0,
                "success_rate": 100.0
            },
            "verification": {
                "total_verifications": 5,
                "successful_verifications": 5,
                "multi_chain_consensus": 5,
                "consensus_rate": 100.0
            }
        }
    except Exception as e:
        logger.error("blockchain_overview_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to get blockchain overview")
