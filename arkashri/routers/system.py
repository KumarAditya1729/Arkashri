# pyre-ignore-all-errors
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from arkashri.db import get_session
from arkashri.models import (
    ClientRole,
    FormulaRegistry,
    RuleRegistry,
    WeightSet,
    WeightEntry,
    SignalType,
    ModelRegistry,
    ModelStatus,
    AgentProfile,
)
from arkashri.schemas import SystemBootstrapResponse
from arkashri.services.canonical import hash_object
from arkashri.dependencies import require_api_client, AuthContext, _audit_registry_change, AGENT_CATALOG

router = APIRouter()

@router.post("/bootstrap/minimal", response_model=SystemBootstrapResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_minimal(
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
) -> SystemBootstrapResponse:
    formula_created = False
    rule_created = False
    weight_set_created = False
    model_created = False

    active_formula = await session.scalar(
        select(FormulaRegistry).where(FormulaRegistry.is_active.is_(True)).order_by(FormulaRegistry.version.desc()).limit(1)
    )
    if active_formula is None:
        next_formula_version = int(await session.scalar(select(func.coalesce(func.max(FormulaRegistry.version), 0))) or 0) + 1
        await session.execute(update(FormulaRegistry).values(is_active=False))
        formula_text = (
            "FinalRisk = clamp(sum(DETERMINISTIC) + sum(ML) + sum(TREND), 0, 100); "
            "deterministic>=0.7, ml<=0.2, trend<=0.1"
        )
        session.add(
            FormulaRegistry(
                version=next_formula_version,
                formula_text=formula_text,
                formula_hash=hash_object(
                    {
                        "version": next_formula_version,
                        "formula_text": formula_text,
                        "component_caps": {"DETERMINISTIC": 0.7, "ML": 0.2, "TREND": 0.1},
                    }
                ),
                component_caps={"DETERMINISTIC": 0.7, "ML": 0.2, "TREND": 0.1},
                is_active=True,
            )
        )
        formula_created = True

    active_rule = await session.scalar(
        select(RuleRegistry)
        .where(RuleRegistry.rule_key == "high_amount", RuleRegistry.is_active.is_(True))
        .order_by(RuleRegistry.version.desc())
        .limit(1)
    )
    if active_rule is None:
        next_rule_version = int(
            await session.scalar(
                select(func.coalesce(func.max(RuleRegistry.version), 0)).where(RuleRegistry.rule_key == "high_amount")
            )
            or 0
        ) + 1
        await session.execute(update(RuleRegistry).where(RuleRegistry.rule_key == "high_amount").values(is_active=False))
        session.add(
            RuleRegistry(
                rule_key="high_amount",
                version=next_rule_version,
                name="High Amount Transaction",
                description="Flags large transactions for deterministic floor risk.",
                expression={"field": "txn.amount", "op": "gte", "value": 100000},
                signal_value=1.0,
                severity_floor=75.0,
                is_active=True,
            )
        )
        rule_created = True

    active_weight_set = await session.scalar(
        select(WeightSet).where(WeightSet.is_active.is_(True)).order_by(WeightSet.version.desc()).limit(1)
    )
    if active_weight_set is None:
        next_weight_version = int(await session.scalar(select(func.coalesce(func.max(WeightSet.version), 0))) or 0) + 1
        await session.execute(update(WeightSet).values(is_active=False))
        weight_entries = [
            {"signal_type": "DETERMINISTIC", "signal_key": "high_amount", "weight": 0.8},
            {"signal_type": "ML", "signal_key": "fraud_anomaly", "weight": 0.2},
        ]
        weight_set = WeightSet(
            version=next_weight_version,
            weight_hash=hash_object({"version": next_weight_version, "entries": weight_entries}),
            is_active=True,
        )
        session.add(weight_set)
        await session.flush()
        session.add(
            WeightEntry(
                weight_set_id=weight_set.id,
                signal_type=SignalType.DETERMINISTIC,
                signal_key="high_amount",
                weight=0.8,
            )
        )
        session.add(
            WeightEntry(
                weight_set_id=weight_set.id,
                signal_type=SignalType.ML,
                signal_key="fraud_anomaly",
                weight=0.2,
            )
        )
        weight_set_created = True

    active_model = await session.scalar(
        select(ModelRegistry)
        .where(ModelRegistry.model_key == "fraud_detector", ModelRegistry.status == ModelStatus.ACTIVE)
        .order_by(ModelRegistry.version.desc())
        .limit(1)
    )
    if active_model is None:
        next_model_version = int(
            await session.scalar(
                select(func.coalesce(func.max(ModelRegistry.version), 0)).where(ModelRegistry.model_key == "fraud_detector")
            )
            or 0
        ) + 1
        await session.execute(
            update(ModelRegistry)
            .where(ModelRegistry.model_key == "fraud_detector", ModelRegistry.status == ModelStatus.ACTIVE)
            .values(status=ModelStatus.SHADOW)
        )
        session.add(
            ModelRegistry(
                model_key="fraud_detector",
                version=next_model_version,
                purpose="ML anomaly signal for fraud detection",
                artifact_hash=hash_object({"artifact": "fraud_detector", "version": next_model_version}),
                hyperparams_hash=hash_object({"learning_rate": 0.01, "seed": 42}),
                dataset_fingerprint=hash_object({"dataset": "baseline_fraud_training_set_v1"}),
                feature_schema_hash=hash_object({"schema": "txn_amount,txn_country,vendor_id,timestamp"}),
                metrics={"auc": 0.91},
                fairness_metrics={"parity_gap": 0.03},
                status=ModelStatus.ACTIVE,
                lower_bound=0.0,
                upper_bound=1.0,
            )
        )
        model_created = True

    existing_keys = set(await session.scalars(select(AgentProfile.agent_key)))
    agents_inserted = 0
    for item in AGENT_CATALOG:
        if item["agent_key"] in existing_keys:
            continue
        session.add(
            AgentProfile(
                agent_key=item["agent_key"],
                name=item["name"],
                domain=item["domain"],
                is_active=True,
            )
        )
        agents_inserted += 1

    await _audit_registry_change(
        session,
        event_type="SYSTEM_BOOTSTRAP_MINIMAL",
        entity_type="system",
        entity_id="bootstrap",
        payload={
            "formula_created": formula_created,
            "rule_created": rule_created,
            "weight_set_created": weight_set_created,
            "model_created": model_created,
            "agents_inserted": agents_inserted,
        },
    )

    await session.commit()
    return SystemBootstrapResponse(
        formula_created=formula_created,
        rule_created=rule_created,
        weight_set_created=weight_set_created,
        model_created=model_created,
        agents_inserted=agents_inserted,
    )
