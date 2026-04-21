# pyre-ignore-all-errors
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from datetime import datetime

from arkashri.db import get_session
from arkashri.models import ClientRole, Decision, DecisionOverride
from arkashri.schemas import DecisionOverrideCreate, DecisionOverrideOut
from arkashri.dependencies import require_api_client, AuthContext
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/decisions/{decision_id}/override", response_model=DecisionOverrideOut, status_code=status.HTTP_201_CREATED)
async def record_decision_override(
    decision_id: str,
    payload: DecisionOverrideCreate,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> DecisionOverrideOut:
    """
    Records a human override of an AI-generated risk decision.
    Mandatory for PCAOB/ISA compliance demonstrating Professional Skepticism.
    """
    # 1. Fetch original decision
    stmt = select(Decision).options(joinedload(Decision.transaction)).where(Decision.id == decision_id)
    decision = (await session.scalars(stmt)).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found.")
        
    # 2. Check for existing override
    stmt_existing = select(DecisionOverride).where(DecisionOverride.decision_id == decision_id)
    existing = (await session.scalars(stmt_existing)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Decision has already been overridden.")

    # 3. Create Override Record
    # Note: RLS ensures we only modify rows for our active tenant
    tenant_id = auth.tenant_id
    jurisdiction = decision.transaction.jurisdiction if decision.transaction else "UNKNOWN"

    override = DecisionOverride(
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        decision_id=decision_id,
        original_risk_score=decision.final_risk,
        original_confidence=decision.confidence,
        overridden_risk_score=payload.overridden_risk_score,
        overridden_by_user=auth.client_name,
        override_reason=payload.override_reason,
        reviewer_confirmation=payload.reviewer_confirmation
    )
    
    session.add(override)
    await session.commit()
    await session.refresh(override)
    
    logger.info(f"Professional Skepticism Override Recorded for Decision {decision_id} by {auth.client_name}")
    return DecisionOverrideOut.model_validate(override)

@router.get("/reports/skepticism", response_model=dict)
async def generate_skepticism_report(
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> dict:
    """
    Generates the Professional Skepticism Report required for Regulatory Submission.
    Lists all downgraded risks and bypassed exceptions.
    """
    tenant_id = auth.tenant_id
    
    # Due to RLS, simply selecting all overrides automatically filters by tenant at the kernel level
    stmt = select(DecisionOverride).order_by(DecisionOverride.override_timestamp.desc())
    overrides = (await session.scalars(stmt)).all()
    
    report = {
        "metadata": {
            "tenant_id": tenant_id,
            "report_generated_at": datetime.now().isoformat(),
            "regulatory_purpose": "PCAOB Standard No. 3 / ISA 200 - Professional Skepticism Evidence"
        },
        "metrics": {
            "total_overrides": len(overrides),
            "downgraded_high_risks": len([o for o in overrides if o.original_risk_score >= 8.0 and o.overridden_risk_score < 8.0]),
            "upgraded_low_risks": len([o for o in overrides if o.original_risk_score < 5.0 and o.overridden_risk_score >= 5.0]),
        },
        "overrides_by_auditor": {},
        "override_log": [
            {
                "decision_id": str(o.decision_id),
                "original_score": o.original_risk_score,
                "overridden_score": o.overridden_risk_score,
                "reason": o.override_reason,
                "auditor": o.overridden_by_user,
                "timestamp": o.override_timestamp.isoformat(),
                "reviewer_confirmation_received": o.reviewer_confirmation
            }
            for o in overrides
        ]
    }
    
    for o in overrides:
        auditor = o.overridden_by_user
        current: int = report["overrides_by_auditor"].get(auditor, 0) # type: ignore
        report["overrides_by_auditor"][auditor] = current + 1 # type: ignore
        
    return report
