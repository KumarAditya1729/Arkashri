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
async def test_generate_udin_for_final_statutory_report_and_verify_public(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)
    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="UDIN Ready Private Limited",
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
    workspace["working_papers"][0]["status"] = "FINAL"
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
    report_response = await async_client.post(
        f"/api/v1/reporting/engagements/{engagement.id}/statutory-audit",
        json={"allow_draft": False},
    )
    assert report_response.status_code == 201
    report_body = report_response.json()
    report_id = report_body["id"]
    report_hash = report_body["report_hash"]

    udin_response = await async_client.post(
        f"/api/v1/reporting/reports/{report_id}/udin/generate",
        json={"member_id": "FCA123456"},
    )
    assert udin_response.status_code == 201
    udin_response_body = udin_response.json()
    udin_payload = udin_response_body["report_payload"]["udin"]
    report_hash = udin_response_body["report_hash"]
    assert udin_payload["status"] == "GENERATED"
    assert udin_payload["mode"] == "ASSISTED"

    read_response = await async_client.get(f"/api/v1/reporting/reports/{report_id}/udin")
    assert read_response.status_code == 200
    assert read_response.json()["udin"]["number"] == udin_payload["number"]

    public_verify = await async_client.get(f"/api/v1/reporting/public/report-verify/{report_hash}")
    assert public_verify.status_code == 200
    verify_payload = public_verify.json()
    assert verify_payload["report_integrity"]["match"] is True
    assert verify_payload["udin"]["number"] == udin_payload["number"]
    assert verify_payload["seal"]["status"] in {"NOT_SEALED", "ERROR", "NOT_SEALED"}


@pytest.mark.asyncio
async def test_udin_generation_blocked_for_draft_report(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)
    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="UDIN Draft Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)
    await bootstrap_india_audit_workspace(db_session, engagement_id=engagement.id, actor_id="tester")

    report_response = await async_client.post(
        f"/api/v1/reporting/engagements/{engagement.id}/statutory-audit",
        json={"allow_draft": True},
    )
    assert report_response.status_code == 201
    report_id = report_response.json()["id"]

    udin_response = await async_client.post(
        f"/api/v1/reporting/reports/{report_id}/udin/generate",
        json={},
    )
    assert udin_response.status_code == 400
    assert "draft report" in udin_response.json()["detail"].lower()
