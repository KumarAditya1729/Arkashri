from __future__ import annotations

import pytest
from sqlalchemy import select

from arkashri.models import AuditEvent, Engagement, EngagementStatus, EngagementType, StandardsFramework
from arkashri.services.specialist_audit_engine import build_specialist_workprogram, get_specialist_engine_catalog


def test_specialist_catalog_covers_previous_roadmap_audits() -> None:
    catalog = get_specialist_engine_catalog()
    audit_types = {item["audit_type"] for item in catalog["audit_types"]}

    assert {
        "penetration_testing",
        "smart_contract_audit",
        "algorithm_audit",
        "digital_forensics",
        "data_leak_investigation",
        "autonomous_control_testing",
        "model_risk_audit",
    } <= audit_types


def test_specialist_workprogram_has_execution_depth() -> None:
    workprogram = build_specialist_workprogram("smart_contract_audit")

    assert workprogram["safe_mode"] is True
    assert len(workprogram["evidence_checklist"]) >= 5
    assert len(workprogram["test_program"]) >= 5
    assert len(workprogram["risk_register"]) >= 4
    assert len(workprogram["closure_gates"]) >= 4
    assert len(workprogram["workprogram_hash"]) == 64


@pytest.mark.asyncio
async def test_specialist_workprogram_api_records_audit_event(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)
    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Specialist Client Private Limited",
        engagement_type=EngagementType.IT_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    catalog = await async_client.get("/api/v1/specialist-audits/catalog")
    assert catalog.status_code == 200, catalog.text

    preview = await async_client.get("/api/v1/specialist-audits/penetration_testing/workprogram")
    assert preview.status_code == 200, preview.text
    assert preview.json()["human_review_required"] is True

    run = await async_client.post(
        f"/api/v1/specialist-audits/engagements/{engagement.id}/run",
        json={"audit_type": "penetration_testing", "context": {"authorized_scope": "staging app only"}},
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["run_id"]
    assert body["workprogram"]["scope_context"]["authorized_scope"] == "staging app only"

    event = await db_session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "SPECIALIST_AUDIT_WORKPROGRAM_GENERATED")
    )
    assert event is not None
    assert event.payload["audit_type"] == "penetration_testing"
