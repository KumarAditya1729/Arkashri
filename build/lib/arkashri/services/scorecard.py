from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import (
    AgentProfile,
    Decision,
    ExceptionCase,
    ExceptionStatus,
    ModelRegistry,
    ModelStatus,
    ReportJob,
    Transaction,
)


@dataclass
class ScorecardMetrics:
    automation_rate: float
    coverage_rate: float
    mean_audit_cycle_days: float | None
    active_agents: int
    has_ml_model: bool
    has_automated_reports: bool
    concurrent_audit_target: str
    setup_time_target_days: int


async def compute_scorecard(session: AsyncSession, tenant_id: str, jurisdiction: str) -> ScorecardMetrics:
    total_txn = int(
        await session.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.tenant_id == tenant_id,
                Transaction.jurisdiction == jurisdiction,
            )
        )
        or 0
    )
    total_decisions = int(
        await session.scalar(
            select(func.count(Decision.id))
            .join(Transaction, Decision.transaction_id == Transaction.id)
            .where(Transaction.tenant_id == tenant_id, Transaction.jurisdiction == jurisdiction)
        )
        or 0
    )
    open_exceptions = int(
        await session.scalar(
            select(func.count(ExceptionCase.id)).where(
                ExceptionCase.tenant_id == tenant_id,
                ExceptionCase.jurisdiction == jurisdiction,
                ExceptionCase.status == ExceptionStatus.OPEN,
            )
        )
        or 0
    )

    result = await session.scalars(
        select(ExceptionCase).where(
            ExceptionCase.tenant_id == tenant_id,
            ExceptionCase.jurisdiction == jurisdiction,
            ExceptionCase.status == ExceptionStatus.RESOLVED,
            ExceptionCase.resolved_at.is_not(None),
        )
    )
    resolved_cases = list(result)
    cycle_days: list[float] = []
    for case in resolved_cases:
        if case.resolved_at is not None:
            delta = case.resolved_at - case.opened_at
            cycle_days.append(delta.total_seconds() / 86400.0)

    mean_cycle = round(sum(cycle_days) / len(cycle_days), 6) if cycle_days else None
    automation_rate = round((total_decisions - open_exceptions) / total_decisions, 6) if total_decisions else 0.0
    coverage_rate = round(total_decisions / total_txn, 6) if total_txn else 0.0

    active_agents = int(await session.scalar(select(func.count(AgentProfile.id)).where(AgentProfile.is_active.is_(True))) or 0)
    has_ml_model = await session.scalar(select(ModelRegistry.id).where(ModelRegistry.status == ModelStatus.ACTIVE).limit(1)) is not None
    has_reports = (
        await session.scalar(
            select(ReportJob.id).where(ReportJob.tenant_id == tenant_id, ReportJob.jurisdiction == jurisdiction).limit(1)
        )
    ) is not None

    return ScorecardMetrics(
        automation_rate=automation_rate,
        coverage_rate=coverage_rate,
        mean_audit_cycle_days=mean_cycle,
        active_agents=active_agents,
        has_ml_model=has_ml_model,
        has_automated_reports=has_reports,
        concurrent_audit_target="50+",
        setup_time_target_days=1,
    )
