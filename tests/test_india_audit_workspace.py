import uuid

import pytest
from sqlalchemy import select

from arkashri.models import (
    Engagement,
    EngagementPhase,
    EngagementStatus,
    EngagementType,
    ProfessionalJudgment,
    JudgmentStatus,
    StandardsFramework,
)
from arkashri.services.engagement_workflow import WorkflowViolation, transition_engagement
from arkashri.services.india_audit_workspace import (
    bootstrap_india_audit_workspace,
    compute_workspace_readiness,
    get_india_workspace,
    update_workspace_checklist_item,
)


@pytest.mark.asyncio
async def test_bootstrap_india_workspace_creates_phases_and_sections(db_session) -> None:
    engagement = Engagement(
        tenant_id="tenant-india",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Alpha Components Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    engagement = await bootstrap_india_audit_workspace(
        db_session,
        engagement_id=engagement.id,
        actor_id="workspace-bot",
    )
    workspace = get_india_workspace(engagement)

    assert workspace["template_version"] == "india_statutory_v1"
    assert len(workspace["checklist_sections"]) >= 5
    assert any(section["section_code"] == "CARO2020" for section in workspace["checklist_sections"])
    assert len(workspace["working_papers"]) >= 5
    phases = list(
        await db_session.scalars(
            select(EngagementPhase).where(EngagementPhase.engagement_id == engagement.id)
        )
    )
    assert len(phases) >= 6


@pytest.mark.asyncio
async def test_workspace_readiness_updates_when_checklist_completed(db_session) -> None:
    engagement = Engagement(
        tenant_id="tenant-india-2",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Beta Engineering Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)
    engagement = await bootstrap_india_audit_workspace(
        db_session,
        engagement_id=engagement.id,
        actor_id="workspace-bot",
    )

    readiness = compute_workspace_readiness(engagement)
    assert readiness["is_report_ready"] is False
    assert readiness["required_checklist_completed"] == 0

    workspace = get_india_workspace(engagement)
    first_code = workspace["checklist_sections"][0]["items"][0]["item_code"]
    await update_workspace_checklist_item(
        db_session,
        engagement_id=engagement.id,
        item_code=first_code,
        status="COMPLETED",
        response=True,
        notes="Captured on file.",
        actor_id="user-1",
    )
    refreshed = await db_session.get(Engagement, engagement.id)
    updated_workspace = get_india_workspace(refreshed)
    updated_item = updated_workspace["checklist_sections"][0]["items"][0]

    assert updated_item["status"] == "COMPLETED"
    assert updated_item["response"] is True
    assert updated_item["updated_by"] == "user-1"


@pytest.mark.asyncio
async def test_review_transition_requires_workspace_completion_when_present(db_session) -> None:
    engagement = Engagement(
        tenant_id="tenant-india-3",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Gamma Manufacturing Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.VERIFIED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)
    await bootstrap_india_audit_workspace(
        db_session,
        engagement_id=engagement.id,
        actor_id="workspace-bot",
    )

    judgment = ProfessionalJudgment(
        engagement_id=engagement.id,
        area="Revenue recognition",
        description="Management cut-off judgments reviewed.",
        ai_confidence=92.5,
        status=JudgmentStatus.SIGNED,
        signed_by="partner-1",
    )
    db_session.add(judgment)
    await db_session.commit()

    with pytest.raises(WorkflowViolation, match="India audit workspace is incomplete"):
        await transition_engagement(
            db_session,
            engagement_id=engagement.id,
            target_status=EngagementStatus.REVIEWED,
            actor_id=str(uuid.uuid4()),
        )
