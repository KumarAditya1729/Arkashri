import pytest
from sqlalchemy import select

from arkashri.models import Engagement, EngagementStatus, EngagementType, StandardsFramework, Transaction
from arkashri.services.tally_ingestion import parse_trial_balance_xml, parse_vouchers_xml, summarize_trial_balance

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
          <CREDIT>150000.00</CREDIT>
          <CLOSINGBALANCE>150000.00 Cr</CLOSINGBALANCE>
        </LEDGER>
        <LEDGER>
          <NAME>Sundry Debtors</NAME>
          <PARENT>Current Assets</PARENT>
          <OPENINGBALANCE>0.00</OPENINGBALANCE>
          <DEBIT>150000.00</DEBIT>
          <CREDIT>0.00</CREDIT>
          <CLOSINGBALANCE>150000.00 Dr</CLOSINGBALANCE>
        </LEDGER>
      </COLLECTION>
    </DATA>
  </BODY>
</ENVELOPE>
""".strip()

VOUCHERS_XML = """
<ENVELOPE>
  <BODY>
    <DATA>
      <COLLECTION>
        <VOUCHER>
          <DATE>20260401</DATE>
          <VOUCHERNUMBER>JV-001</VOUCHERNUMBER>
          <VOUCHERTYPENAME>Journal</VOUCHERTYPENAME>
          <NARRATION>Year-end sales adjustment</NARRATION>
          <PARTYLEDGERNAME>ABC Traders</PARTYLEDGERNAME>
          <GSTREGISTRATIONNUMBER>27ABCDE1234F1Z5</GSTREGISTRATIONNUMBER>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Sundry Debtors</LEDGERNAME>
            <AMOUNT>150000.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Sales</LEDGERNAME>
            <AMOUNT>-150000.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
        </VOUCHER>
      </COLLECTION>
    </DATA>
  </BODY>
</ENVELOPE>
""".strip()

UNBALANCED_VOUCHERS_XML = """
<ENVELOPE>
  <BODY>
    <DATA>
      <COLLECTION>
        <VOUCHER>
          <DATE>20260401</DATE>
          <VOUCHERNUMBER>JV-002</VOUCHERNUMBER>
          <VOUCHERTYPENAME>Journal</VOUCHERTYPENAME>
          <NARRATION>Broken voucher</NARRATION>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Sundry Debtors</LEDGERNAME>
            <AMOUNT>1000.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Sales</LEDGERNAME>
            <AMOUNT>-750.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
        </VOUCHER>
      </COLLECTION>
    </DATA>
  </BODY>
</ENVELOPE>
""".strip()


def test_parse_trial_balance_xml_extracts_balanced_lines() -> None:
    lines = parse_trial_balance_xml(TRIAL_BALANCE_XML)
    summary = summarize_trial_balance(lines)

    assert len(lines) == 2
    assert summary["is_balanced"] is True
    assert summary["mismatch_amount"] == 0.0
    assert any(line["mapped_category"] == "revenue" for line in lines)


def test_parse_vouchers_xml_extracts_signed_ledger_lines() -> None:
    lines = parse_vouchers_xml(VOUCHERS_XML)

    assert len(lines) == 2
    assert lines[0]["voucher_number"] == "JV-001"
    assert sorted(line["signed_amount"] for line in lines) == [-150000.0, 150000.0]


@pytest.mark.asyncio
async def test_tally_trial_balance_and_voucher_import_endpoints(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)
    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Pilot Manufacturing Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    tb_response = await async_client.post(
        f"/api/v1/erp/engagements/{engagement.id}/tally/trial-balance/import",
        json={"raw_xml": TRIAL_BALANCE_XML},
    )
    assert tb_response.status_code == 201
    tb_payload = tb_response.json()
    assert tb_payload["summary"]["is_balanced"] is True
    assert tb_payload["summary"]["line_count"] == 2

    voucher_response = await async_client.post(
        f"/api/v1/erp/engagements/{engagement.id}/tally/vouchers/import",
        json={"raw_xml": VOUCHERS_XML},
    )
    assert voucher_response.status_code == 201
    voucher_payload = voucher_response.json()
    assert voucher_payload["summary"]["voucher_count"] == 1
    assert voucher_payload["summary"]["records_ingested"] == 2

    summary_response = await async_client.get(f"/api/v1/erp/engagements/{engagement.id}/tally/summary")
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert "trial_balance" in summary_payload["imports"]
    assert "vouchers" in summary_payload["imports"]

    transactions = list(await db_session.scalars(select(Transaction).order_by(Transaction.created_at.asc())))
    assert len(transactions) == 2
    assert all(txn.payload["engagement_id"] == str(engagement.id) for txn in transactions)
    assert {txn.payload["mapped_category"] for txn in transactions} == {"revenue", "trade_receivables"}


@pytest.mark.asyncio
async def test_tally_voucher_import_rejects_unbalanced_voucher(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)
    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Delta Components Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    response = await async_client.post(
        f"/api/v1/erp/engagements/{engagement.id}/tally/vouchers/import",
        json={"raw_xml": UNBALANCED_VOUCHERS_XML},
    )

    assert response.status_code == 400
    assert "not balanced" in response.json()["detail"]
