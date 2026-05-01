from datetime import datetime, timezone

import pytest

from arkashri.models import Engagement  # noqa: F401 - ensures SQLAlchemy metadata is registered
from arkashri.schemas import EngagementCreate
from arkashri.services.engagement import create_engagement


@pytest.mark.asyncio
async def test_create_engagement_defaults_seven_day_audit_workflow(async_client, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    response = await async_client.post(
        "/api/v1/engagements/engagements",
        json={
            "tenant_id": "default_tenant",
            "jurisdiction": "IN",
            "client_name": "Seven Day Audit Private Limited",
            "engagement_type": "TAX_AUDIT",
            "auditType": "tax_audit",
            "independence_cleared": True,
            "kyc_cleared": True,
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["auditType"] == "tax_audit"
    assert body["targetCompletionDays"] == 7
    assert body["currentDay"] == 1
    assert body["slaStatus"] == "on_track"
    assert body["checklistProgress"] == {}
    assert body["documentProgress"] == {}
    assert body["reviewStatus"] == "pending"
    assert body["reportStatus"] == "not_started"
    assert body["startDate"]
    assert body["dueDate"]


@pytest.mark.asyncio
async def test_create_engagement_uses_authenticated_tenant_for_listing(async_client, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    response = await async_client.post(
        "/api/v1/engagements/engagements",
        headers={"X-Arkashri-Tenant": "operator_tenant"},
        json={
            "tenant_id": "default_tenant",
            "jurisdiction": "IN",
            "client_name": "Visible Tenant Audit Private Limited",
            "engagement_type": "STATUTORY_AUDIT",
            "auditType": "statutory_audit",
            "independence_cleared": True,
            "kyc_cleared": True,
        },
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["tenant_id"] == "operator_tenant"

    visible = await async_client.get(
        "/api/v1/engagements/engagements",
        headers={"X-Arkashri-Tenant": "operator_tenant"},
    )
    assert visible.status_code == 200, visible.text
    assert [item["id"] for item in visible.json()] == [created["id"]]

    hidden = await async_client.get(
        "/api/v1/engagements/engagements",
        headers={"X-Arkashri-Tenant": "default_tenant"},
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json() == []


@pytest.mark.asyncio
async def test_engagement_subresources_are_tenant_scoped(async_client, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    created = await async_client.post(
        "/api/v1/engagements/engagements",
        headers={"X-Arkashri-Tenant": "tenant_a"},
        json={
            "tenant_id": "tenant_a",
            "jurisdiction": "IN",
            "client_name": "Tenant Scoped Audit Private Limited",
            "engagement_type": "STATUTORY_AUDIT",
            "auditType": "statutory_audit",
            "independence_cleared": True,
            "kyc_cleared": True,
        },
    )
    assert created.status_code == 201, created.text
    engagement_id = created.json()["id"]

    blocked_materiality = await async_client.post(
        f"/api/v1/engagements/engagements/{engagement_id}/materiality",
        headers={"X-Arkashri-Tenant": "tenant_b"},
        json={
            "basis": "REVENUE",
            "basis_amount": 1_000_000,
            "overall_percentage": 5,
            "performance_percentage": 75,
            "trivial_threshold_percentage": 5,
        },
    )
    assert blocked_materiality.status_code == 404, blocked_materiality.text

    blocked_risks = await async_client.get(
        f"/api/v1/engagements/{engagement_id}/risks",
        headers={"X-Arkashri-Tenant": "tenant_b"},
    )
    assert blocked_risks.status_code == 404, blocked_risks.text

    blocked_phase = await async_client.post(
        f"/api/v1/engagements/{engagement_id}/phases",
        headers={"X-Arkashri-Tenant": "tenant_b"},
        json={"name": "Planning"},
    )
    assert blocked_phase.status_code == 404, blocked_phase.text

    blocked_coverage = await async_client.get(
        "/api/v1/metrics/coverage/tenant_a/IN",
        headers={"X-Arkashri-Tenant": "tenant_b"},
    )
    assert blocked_coverage.status_code == 403, blocked_coverage.text


@pytest.mark.asyncio
async def test_controls_cannot_link_risks_from_another_engagement(async_client, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    first = await async_client.post(
        "/api/v1/engagements/engagements",
        headers={"X-Arkashri-Tenant": "tenant_control_scope"},
        json={
            "tenant_id": "tenant_control_scope",
            "jurisdiction": "IN",
            "client_name": "Control Scope One Private Limited",
            "engagement_type": "STATUTORY_AUDIT",
            "auditType": "statutory_audit",
            "independence_cleared": True,
            "kyc_cleared": True,
        },
    )
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]

    second = await async_client.post(
        "/api/v1/engagements/engagements",
        headers={"X-Arkashri-Tenant": "tenant_control_scope"},
        json={
            "tenant_id": "tenant_control_scope",
            "jurisdiction": "IN",
            "client_name": "Control Scope Two Private Limited",
            "engagement_type": "STATUTORY_AUDIT",
            "auditType": "statutory_audit",
            "independence_cleared": True,
            "kyc_cleared": True,
        },
    )
    assert second.status_code == 201, second.text
    second_id = second.json()["id"]

    risk = await async_client.post(
        f"/api/v1/engagements/{first_id}/risks",
        headers={"X-Arkashri-Tenant": "tenant_control_scope"},
        json={
            "title": "Revenue recognition cut-off",
            "area": "Revenue",
            "likelihood": "HIGH",
            "impact": "HIGH",
        },
    )
    assert risk.status_code == 201, risk.text

    blocked_control = await async_client.post(
        f"/api/v1/engagements/{second_id}/controls",
        headers={"X-Arkashri-Tenant": "tenant_control_scope"},
        json={
            "title": "Monthly revenue review",
            "area": "Revenue",
            "control_type": "DETECTIVE",
            "risk_id": risk.json()["id"],
        },
    )
    assert blocked_control.status_code == 404, blocked_control.text


@pytest.mark.asyncio
async def test_update_engagement_workflow_persists_progress(async_client, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    created = await async_client.post(
        "/api/v1/engagements/engagements",
        json={
            "tenant_id": "default_tenant",
            "jurisdiction": "IN",
            "client_name": "Progress Audit LLP",
            "engagement_type": "STATUTORY_AUDIT",
            "independence_cleared": True,
            "kyc_cleared": True,
        },
    )
    assert created.status_code == 201, created.text
    engagement_id = created.json()["id"]

    start_date = datetime(2026, 4, 20, tzinfo=timezone.utc).isoformat()
    response = await async_client.patch(
        f"/api/v1/engagements/engagements/{engagement_id}/workflow",
        json={
            "auditType": "stock_audit",
            "startDate": start_date,
            "currentDay": 4,
            "slaStatus": "at_risk",
            "checklistProgress": {"completed": 4, "total": 7},
            "documentProgress": {"uploaded": 3, "required": 6},
            "reviewStatus": "in_review",
            "reportStatus": "draft",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["auditType"] == "stock_audit"
    assert body["currentDay"] == 4
    assert body["slaStatus"] == "at_risk"
    assert body["checklistProgress"] == {"completed": 4, "total": 7}
    assert body["documentProgress"] == {"uploaded": 3, "required": 6}
    assert body["reviewStatus"] == "in_review"
    assert body["reportStatus"] == "draft"

    detail = await async_client.get(f"/api/v1/engagements/engagements/{engagement_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["auditType"] == "stock_audit"


@pytest.mark.asyncio
async def test_rejects_unsupported_audit_type(async_client, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    response = await async_client.post(
        "/api/v1/engagements/engagements",
        json={
            "tenant_id": "default_tenant",
            "jurisdiction": "IN",
            "client_name": "Unsupported Audit LLP",
            "engagement_type": "STATUTORY_AUDIT",
            "auditType": "forensic_review",
            "independence_cleared": True,
            "kyc_cleared": True,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_engagement_survives_optional_rules_snapshot_failure(db_session, monkeypatch) -> None:
    async def fail_snapshot_lookup(*_args, **_kwargs):
        raise RuntimeError("simulated snapshot storage outage")

    monkeypatch.setattr(db_session, "scalars", fail_snapshot_lookup)

    engagement = await create_engagement(
        db_session,
        EngagementCreate(
            tenant_id="default_tenant",
            jurisdiction="IN",
            client_name="Snapshot Failure Private Limited",
            engagement_type="STATUTORY_AUDIT",
            auditType="statutory_audit",
            independence_cleared=True,
            kyc_cleared=True,
        ),
    )

    assert engagement.id is not None
    assert engagement.client_name == "Snapshot Failure Private Limited"
    assert engagement.audit_type.value == "statutory_audit"
