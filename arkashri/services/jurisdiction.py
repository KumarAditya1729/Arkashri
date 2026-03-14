# pyre-ignore-all-errors
import uuid
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import RegulatoryFramework, CrossBorderPolicy, PolicyEnforcementAction
from arkashri.schemas import (
    RegulatoryFrameworkCreate,
    RegulatoryFrameworkOut,
    CrossBorderPolicyCreate,
    CrossBorderPolicyOut,
)


async def create_regulatory_framework(session: AsyncSession, payload: RegulatoryFrameworkCreate) -> RegulatoryFrameworkOut:
    framework = RegulatoryFramework(
        jurisdiction=payload.jurisdiction,
        framework_type=payload.framework_type,
        name=payload.name,
        description=payload.description,
        authority=payload.authority,
        is_active=payload.is_active,
    )
    session.add(framework)
    await session.commit()
    await session.refresh(framework)
    return RegulatoryFrameworkOut.from_orm(framework)


async def get_regulatory_framework(session: AsyncSession, framework_id: uuid.UUID) -> RegulatoryFrameworkOut | None:
    framework = await session.scalar(select(RegulatoryFramework).where(RegulatoryFramework.id == framework_id))
    if framework:
        return RegulatoryFrameworkOut.from_orm(framework)
    return None


async def get_frameworks_by_jurisdiction(session: AsyncSession, jurisdiction: str) -> list[RegulatoryFrameworkOut]:
    result = await session.scalars(
        select(RegulatoryFramework).where(RegulatoryFramework.jurisdiction == jurisdiction, RegulatoryFramework.is_active.is_(True))
    )
    frameworks = result.all()
    return [RegulatoryFrameworkOut.from_orm(f) for f in frameworks]


async def create_cross_border_policy(session: AsyncSession, payload: CrossBorderPolicyCreate) -> CrossBorderPolicyOut:
    policy = CrossBorderPolicy(
        source_jurisdiction=payload.source_jurisdiction,
        target_jurisdiction=payload.target_jurisdiction,
        policy_name=payload.policy_name,
        enforcement_action=payload.enforcement_action,
        constraint_details=payload.constraint_details,
        is_active=payload.is_active,
    )
    session.add(policy)
    await session.commit()
    await session.refresh(policy)
    return CrossBorderPolicyOut.from_orm(policy)


async def evaluate_cross_border_constraints(
    session: AsyncSession, source_jurisdiction: str, target_jurisdiction: str
) -> dict:
    result = await session.scalars(
        select(CrossBorderPolicy).where(
            CrossBorderPolicy.source_jurisdiction == source_jurisdiction,
            CrossBorderPolicy.target_jurisdiction == target_jurisdiction,
            CrossBorderPolicy.is_active.is_(True),
        )
    )
    policies = result.all()

    response: dict[str, Any] = {
        "allowed": True,
        "enforcement_actions": [],
        "constraints": []
    }

    for policy in policies:
        response["enforcement_actions"].append(policy.enforcement_action)
        response["constraints"].append(policy.constraint_details)
        if policy.enforcement_action == PolicyEnforcementAction.BLOCK:
            response["allowed"] = False

    return response
