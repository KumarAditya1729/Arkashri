from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import AuditPlaybook, SectorControl, EngagementType
from arkashri.schemas import (
    AuditPlaybookCreate,
    AuditPlaybookOut,
    SectorControlCreate,
    SectorControlOut,
)


async def create_playbook(session: AsyncSession, payload: AuditPlaybookCreate) -> AuditPlaybookOut:
    playbook = AuditPlaybook(
        audit_type=payload.audit_type,
        sector=payload.sector,
        playbook_name=payload.playbook_name,
        description=payload.description,
        workflow_template_id=payload.workflow_template_id,
        required_phases=payload.required_phases,
        is_active=payload.is_active,
        version=payload.version,
    )
    session.add(playbook)
    await session.commit()
    await session.refresh(playbook)
    return AuditPlaybookOut.from_orm(playbook)


async def generate_playbook_for_engagement(
    session: AsyncSession, audit_type: EngagementType, sector: str | None = None
) -> AuditPlaybookOut | None:
    query = select(AuditPlaybook).where(
        AuditPlaybook.audit_type == audit_type,
        AuditPlaybook.is_active.is_(True)
    )
    
    if sector:
        # Prefer a sector-specific playbook, fallback to generic
        query = query.where((AuditPlaybook.sector == sector) | (AuditPlaybook.sector.is_(None)))
        query = query.order_by(AuditPlaybook.sector.desc()) # Sector non-nulls first

    result = await session.scalars(query)
    playbook = result.first()
    if playbook:
        return AuditPlaybookOut.from_orm(playbook)
    return None


async def create_sector_control(session: AsyncSession, payload: SectorControlCreate) -> SectorControlOut:
    control = SectorControl(
        sector=payload.sector,
        control_code=payload.control_code,
        control_name=payload.control_name,
        description=payload.description,
        risk_mapping=payload.risk_mapping,
        test_procedures=payload.test_procedures,
        is_active=payload.is_active,
    )
    session.add(control)
    await session.commit()
    await session.refresh(control)
    return SectorControlOut.from_orm(control)


async def get_sector_controls(session: AsyncSession, sector: str) -> list[SectorControlOut]:
    result = await session.scalars(
        select(SectorControl).where(SectorControl.sector == sector, SectorControl.is_active.is_(True))
    )
    controls = result.all()
    return [SectorControlOut.from_orm(c) for c in controls]
