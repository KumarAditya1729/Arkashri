import pytest

from arkashri.models import Engagement, EngagementStatus, EngagementType, EvidenceRecord, StandardsFramework, Transaction
from arkashri.services.gst_reconciliation import GST_RECON_KEY


@pytest.mark.asyncio
async def test_books_health_check_blocks_messy_books_and_creates_client_queries(
    async_client,
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Messy Books Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    response = await async_client.post(
        f"/api/v1/readiness/engagements/{engagement.id}/books-health",
        json={"create_client_queries": True},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["seven_day_sprint_status"] == "BLOCKED"
    assert payload["critical_blocker_count"] >= 3
    assert payload["client_query_count_created"] >= 3
    assert {issue["category"] for issue in payload["issues"]} >= {"BANK", "GST", "LEDGER", "EVIDENCE"}
    assert "Close all critical blockers before report drafting." in payload["next_actions"]

    workflow = await async_client.get(f"/api/v1/portal/engagements/{engagement.id}/workflow")
    assert workflow.status_code == 200
    assert workflow.json()["workflow"]["open_query_count"] == payload["client_query_count_created"]

    rerun = await async_client.post(
        f"/api/v1/readiness/engagements/{engagement.id}/books-health",
        json={"create_client_queries": True},
    )
    assert rerun.status_code == 201, rerun.text
    assert rerun.json()["client_query_count_created"] == 0


@pytest.mark.asyncio
async def test_books_health_check_marks_clean_sprint_ready(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Clean Books Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
        state_metadata={
            GST_RECON_KEY: {
                "gstr1_vs_books": {
                    "reconciled_at": "2026-04-10T00:00:00+00:00",
                    "summary": {"matched_count": 1, "mismatch_count": 0, "risk_breakdown": {}},
                    "mismatches": [],
                },
                "gstr2b_vs_itc": {
                    "reconciled_at": "2026-04-10T00:00:00+00:00",
                    "summary": {"matched_count": 1, "mismatch_count": 0, "risk_breakdown": {}},
                    "mismatches": [],
                },
            }
        },
    )
    db_session.add(engagement)
    await db_session.flush()
    db_session.add_all(
        [
            Transaction(
                tenant_id="default_tenant",
                jurisdiction="IN",
                payload={
                    "engagement_id": str(engagement.id),
                    "ref": "BANK-001",
                    "date": "2026-04-01",
                    "signed_amount": 12345.67,
                    "amount": 12345.67,
                    "erp_system": "BANK_STATEMENT",
                    "account_name": "HDFC Bank",
                },
                payload_hash="bankstmt-clean-001",
            ),
            Transaction(
                tenant_id="default_tenant",
                jurisdiction="IN",
                payload={
                    "engagement_id": str(engagement.id),
                    "ref": "BOOK-BANK-001",
                    "date": "2026-04-01",
                    "signed_amount": 12345.67,
                    "mapped_category": "cash_and_bank",
                    "account_name": "HDFC Bank",
                },
                payload_hash="bankbook-clean-001",
            ),
        ]
    )
    db_session.add(
        EvidenceRecord(
            engagement_id=engagement.id,
            tenant_id="default_tenant",
            evd_ref="EVD-001",
            file_name="bank-statement.pdf",
            file_path="/tmp/bank-statement.pdf",
            file_size_kb="12",
            evidence_type="Bank Statement",
            ev_status="Reviewed",
            uploaded_by="CA",
        )
    )
    await db_session.commit()

    response = await async_client.post(
        f"/api/v1/readiness/engagements/{engagement.id}/books-health",
        json={"create_client_queries": False},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["seven_day_sprint_status"] == "READY"
    assert payload["critical_blocker_count"] == 0
    assert payload["readiness_score"] >= 85
    assert payload["categories"]["gst_reconciliation"]["score"] == 100

    history = await async_client.get(f"/api/v1/readiness/engagements/{engagement.id}/books-health")
    assert history.status_code == 200
    assert history.json()["health_checks"][0]["seven_day_sprint_status"] == "READY"
