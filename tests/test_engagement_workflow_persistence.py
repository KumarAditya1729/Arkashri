from datetime import datetime, timezone

import pytest

from arkashri.models import Engagement  # noqa: F401 - ensures SQLAlchemy metadata is registered


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
