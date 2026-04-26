import copy
from datetime import datetime, timezone

import pytest

from arkashri.models import Engagement, EngagementStatus, EngagementType, StandardsFramework
from arkashri.services.india_audit_workspace import bootstrap_india_audit_workspace, get_india_workspace

TRIAL_BALANCE_XML = """
<ENVELOPE>
  <BODY>
    <DATA>
      <COLLECTION>
        <LEDGER>
          <NAME>Sales</NAME>
          <PARENT>Revenue</PARENT>
          <OPENINGBALANCE>0.00</OPENINGBALANCE>
          <DEBIT>0.00</DEBIT>
          <CREDIT>118000.00</CREDIT>
          <CLOSINGBALANCE>118000.00 Cr</CLOSINGBALANCE>
        </LEDGER>
        <LEDGER>
          <NAME>Sundry Debtors</NAME>
          <PARENT>Current Assets</PARENT>
          <OPENINGBALANCE>0.00</OPENINGBALANCE>
          <DEBIT>118000.00</DEBIT>
          <CREDIT>0.00</CREDIT>
          <CLOSINGBALANCE>118000.00 Dr</CLOSINGBALANCE>
        </LEDGER>
      </COLLECTION>
    </DATA>
  </BODY>
</ENVELOPE>
""".strip()

SALES_VOUCHERS_XML = """
<ENVELOPE>
  <BODY>
    <DATA>
      <COLLECTION>
        <VOUCHER>
          <DATE>20260401</DATE>
          <VOUCHERNUMBER>INV-001</VOUCHERNUMBER>
          <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
          <NARRATION>Sales invoice 1</NARRATION>
          <PARTYLEDGERNAME>ABC Traders</PARTYLEDGERNAME>
          <GSTREGISTRATIONNUMBER>27ABCDE1234F1Z5</GSTREGISTRATIONNUMBER>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Sundry Debtors</LEDGERNAME>
            <AMOUNT>118000.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Sales</LEDGERNAME>
            <AMOUNT>-100000.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Output CGST</LEDGERNAME>
            <AMOUNT>-9000.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Output SGST</LEDGERNAME>
            <AMOUNT>-9000.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
        </VOUCHER>
      </COLLECTION>
    </DATA>
  </BODY>
</ENVELOPE>
""".strip()


@pytest.mark.asyncio
async def test_india_statutory_report_blocks_when_workspace_not_ready(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)
    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Report Blocker Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)
    await bootstrap_india_audit_workspace(db_session, engagement_id=engagement.id, actor_id="tester")

    response = await async_client.post(
        f"/api/v1/reporting/engagements/{engagement.id}/statutory-audit",
        json={"allow_draft": False},
    )

    assert response.status_code == 400
    assert "not ready for final generation" in response.json()["detail"]


@pytest.mark.asyncio
async def test_india_statutory_report_uses_workspace_tally_and_gst(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)
    from arkashri.services.object_storage import object_storage_service
    monkeypatch.setattr(object_storage_service.settings, "upload_dir", "/tmp/arkashri-test-report-artifacts")

    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Report Ready Private Limited",
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

    workspace = copy.deepcopy(get_india_workspace(engagement))
    for section in workspace["checklist_sections"]:
        for item in section["items"]:
            item["status"] = "COMPLETED"
            item["response"] = True
            item["notes"] = "Completed for report generation."
    workspace["working_papers"][0]["status"] = "PREPARED"
    metadata = copy.deepcopy(engagement.state_metadata or {})
    metadata["india_workspace"] = workspace
    engagement.state_metadata = metadata
    db_session.add(engagement)
    await db_session.commit()

    await async_client.post(
        f"/api/v1/erp/engagements/{engagement.id}/tally/trial-balance/import",
        json={"raw_xml": TRIAL_BALANCE_XML},
    )
    await async_client.post(
        f"/api/v1/erp/engagements/{engagement.id}/tally/vouchers/import",
        json={"raw_xml": SALES_VOUCHERS_XML},
    )
    await async_client.post(
        f"/api/v1/gst/engagements/{engagement.id}/reconcile/gstr1-vs-books",
        json={
            "portal_records": [
                {
                    "invoice_no": "INV-001",
                    "gstin": "27ABCDE1234F1Z5",
                    "taxable_value": 100000.0,
                    "tax_amount": 18000.0,
                    "period": "2026-04",
                }
            ]
        },
    )

    response = await async_client.post(
        f"/api/v1/reporting/engagements/{engagement.id}/statutory-audit",
        json={"allow_draft": False},
    )

    assert response.status_code == 201
    report_body = response.json()
    report_id = report_body["id"]
    payload = report_body["report_payload"]
    assert payload["report_type"] == "INDIA_STATUTORY_AUDIT"
    assert payload["is_draft"] is False
    assert payload["workspace_readiness"]["is_report_ready"] is True
    assert "gstr1_vs_books" in payload["report_sections"]["gst_highlights"]
    assert "trial_balance" in payload["report_sections"]["tally_import_summary"]
    assert payload["report_sections"]["caro_annexure"]

    html_artifact = await async_client.get(f"/api/v1/reporting/reports/{report_id}/artifact")
    assert html_artifact.status_code == 200
    html_payload = html_artifact.json()
    assert html_payload["content_type"] == "text/html; charset=utf-8"
    assert "Independent Auditor's Report" in html_payload["artifact_html"]
    assert "Report Ready Private Limited" in html_payload["artifact_html"]
    assert html_payload["verification_url"].endswith(report_body["report_hash"])
    assert html_payload["report_hash"] == report_body["report_hash"]
    assert html_payload["qr_code_data_url"].startswith("data:image/png;base64,")

    pdf_artifact = await async_client.get(f"/api/v1/reporting/reports/{report_id}/artifact?format=pdf")
    assert pdf_artifact.status_code in {200, 503}
    if pdf_artifact.status_code == 200:
        assert pdf_artifact.headers["content-type"].startswith("application/pdf")
        assert pdf_artifact.content.startswith(b"%PDF")
    else:
        assert "PDF rendering is unavailable" in pdf_artifact.json()["detail"]

    persisted_artifact = await async_client.post(f"/api/v1/reporting/reports/{report_id}/artifact/persist")
    assert persisted_artifact.status_code == 200
    artifact_record = persisted_artifact.json()["artifact"]
    assert artifact_record["provider"] == "local"
    assert artifact_record["report_hash"] == report_body["report_hash"]
    assert artifact_record["uri"].endswith(".html")

    await db_session.refresh(engagement)
    stored_artifacts = engagement.state_metadata["report_artifacts"][report_id]
    assert stored_artifacts["html"]["uri"] == artifact_record["uri"]
