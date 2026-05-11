from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from arkashri.models import (
    AuditEvent,
    Engagement,
    EngagementStatus,
    EngagementType,
    ReportJob,
    RiskEntry,
    StandardsFramework,
    ControlEntry,
)


def _csv_bytes() -> bytes:
    return (
        "Txn Date,Narration,Voucher No,Debit,Credit,Ledger Name,Party GSTIN\n"
        "2026-04-01,Sales receipt from customer,RCPT-001,,500000.00,Sales,\n"
        "2026-04-04,Manual cash adjustment,JV-ROUND,100000.00,,Cash Account,\n"
        "2026-04-05,Purchase payment,PAY-001,250000.00,,Vendor Expense,\n"
    ).encode("utf-8")


async def _create_engagement(db_session) -> Engagement:
    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Automation Client Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)
    return engagement


async def _ingest_csv(async_client, engagement: Engagement) -> None:
    response = await async_client.post(
        f"/api/v1/data-refinery/engagements/{engagement.id}/ingest-csv",
        files={"file": ("raw-ledger.csv", _csv_bytes(), "text/csv")},
        data={"source_type": "books_ledger"},
    )
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_big4_automation_pack_previews_readiness(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)
    engagement = await _create_engagement(db_session)
    await _ingest_csv(async_client, engagement)

    response = await async_client.get(f"/api/v1/audit-automation/engagements/{engagement.id}/pack")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engagement_id"] == str(engagement.id)
    assert body["risk_intelligence"]["transaction_count"] == 3
    assert body["risk_intelligence"]["findings"]
    assert body["working_papers"]["schedules"]
    assert body["report_readiness"]["human_review_required"] is True


@pytest.mark.asyncio
async def test_big4_automation_run_creates_risks_controls_and_report(
    async_client,
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)
    engagement = await _create_engagement(db_session)
    await _ingest_csv(async_client, engagement)

    response = await async_client.post(
        f"/api/v1/audit-automation/engagements/{engagement.id}/run",
        json={"create_risks": True, "create_controls": True, "persist_report": True},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created_risk_count"] >= 1
    assert body["created_control_count"] == body["created_risk_count"]
    assert body["report_job_id"]
    assert body["pack"]["report_readiness"]["suggested_opinion_type"] in {
        "UNMODIFIED",
        "QUALIFIED",
        "ADVERSE",
        "DISCLAIMER",
    }

    risks = list(await db_session.scalars(select(RiskEntry).where(RiskEntry.engagement_id == engagement.id)))
    controls = list(await db_session.scalars(select(ControlEntry).where(ControlEntry.engagement_id == engagement.id)))
    report = await db_session.scalar(select(ReportJob).where(ReportJob.id == uuid.UUID(body["report_job_id"])))
    event = await db_session.scalar(select(AuditEvent).where(AuditEvent.event_type == "BIG4_AUTOMATION_PACK_RUN"))

    assert len(risks) == body["created_risk_count"]
    assert len(controls) == body["created_control_count"]
    assert report is not None
    assert report.report_payload["report_type"] == "BIG4_AUTOMATION_PACK"
    assert event is not None
    assert event.payload["created_risk_count"] == body["created_risk_count"]


@pytest.mark.asyncio
async def test_completion_layer_capabilities_sampling_agents_and_response_workflow(
    async_client,
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)
    engagement = await _create_engagement(db_session)
    await _ingest_csv(async_client, engagement)

    capabilities = await async_client.get("/api/v1/audit-automation/capabilities")
    assert capabilities.status_code == 200, capabilities.text
    connector_keys = {item["key"] for item in capabilities.json()["connectors"]}
    assert {"TALLY_PRIME", "ZOHO_BOOKS", "BUSY", "SAP_S4HANA", "ORACLE_FUSION"} <= connector_keys
    assert any(pack["key"] == "PCAOB_SOX" for pack in capabilities.json()["global_compliance_packs"])

    sampling = await async_client.post(
        f"/api/v1/audit-automation/engagements/{engagement.id}/sampling-plan",
        json={"sample_size": 2},
    )
    assert sampling.status_code == 200, sampling.text
    assert sampling.json()["sample_size"] == 2
    assert sampling.json()["method"] == "risk_weighted_deterministic"

    agents = await async_client.post(f"/api/v1/audit-automation/engagements/{engagement.id}/agents/run")
    assert agents.status_code == 200, agents.text
    assert {agent["key"] for agent in agents.json()["agents"]} >= {"revenue_agent", "fraud_agent", "caro_agent"}

    confirmation = await async_client.post(
        f"/api/v1/audit-automation/engagements/{engagement.id}/confirmations",
        json={"counterparty": "HDFC Bank", "amount": 500000, "contact_email": "bank@example.com"},
    )
    assert confirmation.status_code == 201, confirmation.text
    assert confirmation.json()["status"] == "REQUESTED"

    response = await async_client.post(
        f"/api/v1/audit-automation/engagements/{engagement.id}/management-responses",
        json={"finding_code": "ANOMALY_FLAGS", "response_text": "Management will provide support.", "owner": "CFO"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["human_review_required"] is True

    events = list(await db_session.scalars(select(AuditEvent).where(AuditEvent.engagement_id == engagement.id)))
    event_types = {event.event_type for event in events}
    assert {"SAMPLING_PLAN_GENERATED", "AI_AUDIT_AGENTS_RUN", "CONFIRMATION_REQUEST_CREATED", "MANAGEMENT_RESPONSE_RECORDED"} <= event_types

    export = await async_client.get(f"/api/v1/audit-automation/engagements/{engagement.id}/working-papers/export")
    assert export.status_code == 200, export.text
    assert "Working Paper Pack" in export.text
    assert "attachment" in export.headers["content-disposition"]
