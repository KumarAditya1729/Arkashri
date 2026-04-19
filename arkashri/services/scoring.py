# pyre-ignore-all-errors
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import Decision, Transaction
from arkashri.services.risk_engine import compute_risk
from arkashri.services.replay import build_output_hash


async def score_engagement_transactions(
    session: AsyncSession,
    engagement_id: uuid.UUID,
) -> dict[str, Any]:
    """
    Operationalizes the Risk Engine by scoring all transactions for an engagement.
    Creates or updates Decision records with trace logs for explainability.
    Optional ML and trend signals must already be attached to the transaction payload.
    """
    # 1. Fetch transactions linked to this engagement context
    # In Arkashri, transactions are often filtered by tenant or specific engagement metadata.
    # For this operational bridge, we'll fetch transactions for the tenant tied to the engagement.
    from arkashri.models import Engagement
    engagement = await session.get(Engagement, engagement_id)
    if not engagement:
        raise ValueError(f"Engagement {engagement_id} not found")

    stmt = select(Transaction).where(Transaction.tenant_id == engagement.tenant_id)
    transactions = (await session.scalars(stmt)).all()

    scored_count = 0
    high_risk_count = 0

    for txn in transactions:
        payload = txn.payload if isinstance(txn.payload, dict) else {}
        ml_signals = payload.get("ml_signals") or payload.get("_ml_signals") or []
        trend_signals = payload.get("trend_signals") or payload.get("_trend_signals") or []
        
        # 3. Compute Risk
        result = await compute_risk(
            session=session,
            payload=payload,
            ml_signals=ml_signals,
            trend_signals=trend_signals,
            model_stability=1.0,
        )

        # 4. Generate Output Hash for replayability
        output_hash = build_output_hash(txn.payload_hash, result)

        # 5. Persist Decision
        # Check if decision already exists
        decision = await session.scalar(select(Decision).where(Decision.transaction_id == txn.id))
        
        if not decision:
            decision = Decision(
                transaction_id=txn.id,
                final_risk=result.final_risk,
                confidence=result.confidence_breakdown["overall"],
                output_hash=output_hash,
                formula_version=result.formula_version,
                weight_set_version=result.weight_set_version,
                model_versions=result.model_versions,
                rule_snapshot=result.rule_snapshot,
                explanation={
                    "components": result.components_as_dicts(),
                    "confidence_breakdown": result.confidence_breakdown,
                },
                trace_log=result.trace_log,
            )
            session.add(decision)
        else:
            decision.final_risk = result.final_risk
            decision.confidence = result.confidence_breakdown["overall"]
            decision.output_hash = output_hash
            decision.formula_version = result.formula_version
            decision.weight_set_version = result.weight_set_version
            decision.model_versions = result.model_versions
            decision.rule_snapshot = result.rule_snapshot
            decision.explanation = {
                "components": result.components_as_dicts(),
                "confidence_breakdown": result.confidence_breakdown,
            }
            decision.trace_log = result.trace_log
        
        # 🔗 Blockchain Anchoring Hook
        # Anchor the decision for WORM compliance (Write Once Read Many)
        from arkashri.services.multi_chain_blockchain import multi_chain_blockchain_service
        try:
            # We anchor the output_hash which includes the trace_log content
            await multi_chain_blockchain_service.anchor_evidence_multi_chain(
                evidence_hash=output_hash,
                metadata={
                    "transaction_id": str(txn.id),
                    "engagement_id": str(engagement_id),
                    "final_risk": float(result.final_risk),
                    "timestamp": decision.created_at.isoformat() if hasattr(decision, 'created_at') and decision.created_at else ""
                }
            )
        except Exception as e:
            # We don't fail the scoring if blockchain fails, but we log the warning
            # In a production "Hard-Compliance" mode, this could be a blocking failure.
            from structlog import get_logger
            get_logger(__name__).warning("decision_anchoring_failed", transaction_id=str(txn.id), error=str(e))

        scored_count += 1
        if result.final_risk >= 70.0:
            high_risk_count += 1

    await session.commit()
    
    return {
        "transactions_scored": scored_count,
        "high_risk_count": high_risk_count,
        "engagement_id": str(engagement_id),
    }
