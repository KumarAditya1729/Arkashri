from datetime import datetime, timezone

import pytest

from arkashri.models import Engagement, EngagementStatus, EngagementType, StandardsFramework
from arkashri.services.india_audit_workspace import bootstrap_india_audit_workspace, get_india_workspace

VALID_CIN = "U12345MH2020PTC123456"


@pytest.mark.asyncio
async def test_mca_company_master_enriches_engagement(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="MCA Client Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    response = await async_client.post(
        f"/api/v1/mca/engagements/{engagement.id}/company-master",
        json={
            "cin": VALID_CIN,
            "manual_master_data": {
                "company_name": "MCA Client Private Limited",
                "company_status": "Active",
                "registered_office": "Mumbai, Maharashtra",
                "paid_up_capital": 2500000,
                "directors": [{"name": "Asha Mehta", "din": "01234567"}],
                "charges": [{"charge_id": "CHG-1", "amount": 1000000}],
            },
        },
    )

    assert response.status_code == 200
    snapshot = response.json()["mca_company_master"]
    assert snapshot["cin"] == VALID_CIN
    assert snapshot["company_status"] == "ACTIVE"
    assert snapshot["registered_office"] == "Mumbai, Maharashtra"
    assert snapshot["source"] == "MANUAL"

    read_response = await async_client.get(f"/api/v1/mca/engagements/{engagement.id}/company-master")
    assert read_response.status_code == 200
    assert read_response.json()["mca_company_master"]["directors"][0]["name"] == "Asha Mehta"


@pytest.mark.asyncio
async def test_mca_enrichment_rejects_invalid_cin(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Invalid CIN Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    response = await async_client.post(
        f"/api/v1/mca/engagements/{engagement.id}/company-master",
        json={
            "cin": "BAD-CIN",
            "manual_master_data": {"company_name": "Invalid CIN Private Limited"},
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_mca_snapshot_flows_into_india_report(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="MCA Report Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        period_start=datetime(2025, 4, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 3, 31, tzinfo=timezone.utc),
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    engagement = await bootstrap_india_audit_workspace(db_session, engagement_id=engagement.id, actor_id="tester")
    workspace = get_india_workspace(engagement)
    for section in workspace["checklist_sections"]:
        for item in section["items"]:
            item["status"] = "COMPLETED"
            item["response"] = True
            item["notes"] = "Completed."
    workspace["working_papers"][0]["status"] = "PREPARED"
    metadata = engagement.state_metadata or {}
    metadata["india_workspace"] = workspace
    engagement.state_metadata = metadata
    db_session.add(engagement)
    await db_session.commit()

    await async_client.post(
        f"/api/v1/mca/engagements/{engagement.id}/company-master",
        json={
            "cin": VALID_CIN,
            "manual_master_data": {
                "company_name": "MCA Report Private Limited",
                "company_status": "ACTIVE",
                "registered_office": "Pune, Maharashtra",
                "paid_up_capital": 5000000,
            },
        },
    )

    report_response = await async_client.post(
        f"/api/v1/reporting/engagements/{engagement.id}/statutory-audit",
        json={"allow_draft": False},
    )
    assert report_response.status_code == 201
    report_body = report_response.json()
    assert report_body["report_payload"]["mca_company_master"]["cin"] == VALID_CIN

    artifact = await async_client.get(f"/api/v1/reporting/reports/{report_body['id']}/artifact")
    assert artifact.status_code == 200
    assert VALID_CIN in artifact.json()["artifact_html"]
    assert "MCA Company Master" in artifact.json()["artifact_html"]
