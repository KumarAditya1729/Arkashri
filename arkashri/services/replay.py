from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import Decision
from arkashri.services.canonical import hash_object
from arkashri.services.risk_engine import RiskComputationResult, compute_risk


def build_output_hash(payload_hash: str, result: RiskComputationResult) -> str:
    material = {
        "payload_hash": payload_hash,
        "final_risk": result.final_risk,
        "formula_version": result.formula_version,
        "weight_set_version": result.weight_set_version,
        "rule_snapshot": result.rule_snapshot,
        "model_versions": result.model_versions,
        "components": result.components_as_dicts(),
        "confidence": result.confidence_breakdown,
    }
    return hash_object(material)


async def recompute_for_decision(
    session: AsyncSession,
    decision: Decision,
    *,
    score_payload: dict[str, Any],
    payload_hash: str,
) -> tuple[RiskComputationResult, str]:
    result = await compute_risk(
        session,
        payload=score_payload.get("payload", {}),
        ml_signals=score_payload.get("ml_signals", []),
        trend_signals=score_payload.get("trend_signals", []),
        model_stability=float(score_payload.get("model_stability", 1.0)),
        formula_version=decision.formula_version,
        weight_set_version=decision.weight_set_version,
        rule_snapshot=decision.rule_snapshot,
    )

    output_hash = build_output_hash(payload_hash, result)
    return result, output_hash
