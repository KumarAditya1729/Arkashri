import pytest

from arkashri.models import Engagement, EngagementStatus, EngagementType, StandardsFramework
from arkashri.services.whatsapp import WhatsAppDispatchResult


@pytest.mark.asyncio
async def test_client_query_and_approval_workflow(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    async def fake_whatsapp_dispatch(*, to_phone: str, message: str) -> WhatsAppDispatchResult:
        assert to_phone == "+919876543210"
        assert "Arkashri" in message
        return WhatsAppDispatchResult(
            status="SENT",
            provider_message_id="wamid.test",
            error=None,
            dispatched_at="2026-04-26T18:30:00+00:00",
        )

    monkeypatch.setattr("arkashri.routers.client_portal.send_whatsapp_message", fake_whatsapp_dispatch)

    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Client Workflow Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    access_response = await async_client.post(
        f"/api/v1/portal/engagements/{engagement.id}/access",
        json={"client_email": "client@example.com", "expires_in_days": 30},
    )
    assert access_response.status_code == 200
    token = access_response.json()["token"]

    query_response = await async_client.post(
        f"/api/v1/portal/engagements/{engagement.id}/queries",
        json={
            "title": "Need bank confirmation",
            "question": "Please upload the April bank confirmation and final sanction letter.",
            "priority": "HIGH",
            "requested_documents": ["Bank confirmation", "Sanction letter"],
            "client_phone": "+919876543210",
            "portal_url": "https://app.arkashri.example/portal/test-token",
        },
    )
    assert query_response.status_code == 200
    query_id = query_response.json()["query"]["id"]
    assert query_response.json()["query"]["notifications"][0]["status"] == "SENT"

    approval_response = await async_client.post(
        f"/api/v1/portal/engagements/{engagement.id}/approvals",
        json={
            "title": "Approve management representation draft",
            "summary": "Please confirm the draft management representation letter wording.",
            "approval_type": "MANAGEMENT_REPRESENTATION",
            "client_phone": "+919876543210",
            "portal_url": "https://app.arkashri.example/portal/test-token",
        },
    )
    assert approval_response.status_code == 200
    approval_id = approval_response.json()["approval"]["id"]
    assert approval_response.json()["approval"]["notifications"][0]["provider_message_id"] == "wamid.test"

    dashboard_response = await async_client.get(f"/api/v1/portal/dashboard?token={token}")
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["client_requests"]["open_queries"] == 1
    assert dashboard_response.json()["client_requests"]["pending_approvals"] == 1

    requests_response = await async_client.get(f"/api/v1/portal/requests?token={token}")
    assert requests_response.status_code == 200
    assert len(requests_response.json()["queries"]) == 1
    assert len(requests_response.json()["approvals"]) == 1

    client_query_response = await async_client.post(
        f"/api/v1/portal/queries/{query_id}/respond?token={token}",
        json={"response_text": "Uploaded both files and attached note on facility renewal."},
    )
    assert client_query_response.status_code == 200
    assert client_query_response.json()["query"]["status"] == "CLIENT_RESPONDED"

    client_approval_response = await async_client.post(
        f"/api/v1/portal/approvals/{approval_id}/act?token={token}",
        json={"decision": "approved", "decision_notes": "Approved on behalf of management."},
    )
    assert client_approval_response.status_code == 200
    assert client_approval_response.json()["approval"]["status"] == "APPROVED"

    internal_workflow = await async_client.get(f"/api/v1/portal/engagements/{engagement.id}/workflow")
    assert internal_workflow.status_code == 200
    workflow = internal_workflow.json()["workflow"]
    assert workflow["queries"][0]["status"] == "CLIENT_RESPONDED"
    assert workflow["queries"][0]["notifications"][0]["channel"] == "WHATSAPP"
    assert workflow["approvals"][0]["status"] == "APPROVED"
    assert workflow["approvals"][0]["notifications"][0]["status"] == "SENT"


@pytest.mark.asyncio
async def test_internal_query_can_be_closed(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Client Closeout Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    query_response = await async_client.post(
        f"/api/v1/portal/engagements/{engagement.id}/queries",
        json={
            "title": "Need invoice support",
            "question": "Please upload invoice support for the top ten receivables.",
        },
    )
    query_id = query_response.json()["query"]["id"]

    close_response = await async_client.patch(
        f"/api/v1/portal/engagements/{engagement.id}/queries/{query_id}",
        json={"status": "CLOSED", "internal_notes": "Support received and reviewed."},
    )
    assert close_response.status_code == 200
    assert close_response.json()["query"]["status"] == "CLOSED"
    assert close_response.json()["query"]["internal_notes"] == "Support received and reviewed."
