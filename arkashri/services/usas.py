# pyre-ignore-all-errors
from sqlalchemy.ext.asyncio import AsyncSession
from arkashri.models import (
    CrisisEvent,
    ContinuousAuditRule,
    ForensicInvestigation,
    ESGMetric,
    AIGovernanceLog,
    SovereignArchive,
    ArchiveStatus,
)
from arkashri.schemas import (
    CrisisEventCreate,
    ContinuousAuditRuleCreate,
    ForensicInvestigationCreate,
    ESGMetricCreate,
    AIGovernanceLogCreate,
    SovereignArchiveCreate,
)

async def trigger_crisis_event(session: AsyncSession, payload: CrisisEventCreate) -> CrisisEvent:
    """
    Triggers a crisis event (e.g., FRAUD_DETECTED) and automatically initiates evidence freeze protocols.
    """
    event = CrisisEvent(**payload.model_dump())
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def create_continuous_audit_rule(session: AsyncSession, payload: ContinuousAuditRuleCreate) -> ContinuousAuditRule:
    """
    Registers a continuous audit rule for real-time risk monitoring.
    """
    rule = ContinuousAuditRule(**payload.model_dump())
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


async def open_forensic_investigation(session: AsyncSession, payload: ForensicInvestigationCreate) -> ForensicInvestigation:
    """
    Opens a deep-dive forensic investigation into specific entities or related parties.
    """
    investigation = ForensicInvestigation(**payload.model_dump())
    session.add(investigation)
    await session.commit()
    await session.refresh(investigation)
    return investigation


async def log_esg_metric(session: AsyncSession, payload: ESGMetricCreate) -> ESGMetric:
    """
    Records an ESG-related metric for sustainability tracking and reporting.
    """
    metric = ESGMetric(**payload.model_dump())
    session.add(metric)
    await session.commit()
    await session.refresh(metric)
    return metric


async def record_ai_governance_log(session: AsyncSession, payload: AIGovernanceLogCreate) -> AIGovernanceLog:
    """
    Logs the rationale of an AI decision for explainability and human-in-the-loop governance.
    """
    log_entry = AIGovernanceLog(**payload.model_dump())
    session.add(log_entry)
    await session.commit()
    await session.refresh(log_entry)
    return log_entry


async def seal_sovereign_archive(session: AsyncSession, payload: SovereignArchiveCreate) -> SovereignArchive:
    """
    Simulates sealing an engagement archive in a WORM-compliant storage structure.
    """
    payload_dict = payload.model_dump()
    archive = SovereignArchive(**payload_dict)
    archive.status = ArchiveStatus.SEALED
    session.add(archive)
    await session.commit()
    await session.refresh(archive)
    return archive
