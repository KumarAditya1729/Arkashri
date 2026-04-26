import pytest
from sqlalchemy import select

from arkashri.models import Engagement, EngagementStatus, EngagementType, StandardsFramework, Transaction

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

PURCHASE_VOUCHERS_XML = """
<ENVELOPE>
  <BODY>
    <DATA>
      <COLLECTION>
        <VOUCHER>
          <DATE>20260405</DATE>
          <VOUCHERNUMBER>PUR-001</VOUCHERNUMBER>
          <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
          <NARRATION>Purchase invoice 1</NARRATION>
          <PARTYLEDGERNAME>Supply Co</PARTYLEDGERNAME>
          <GSTREGISTRATIONNUMBER>27PQRSX1234L1Z9</GSTREGISTRATIONNUMBER>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Raw Material Purchase</LEDGERNAME>
            <AMOUNT>50000.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Input CGST</LEDGERNAME>
            <AMOUNT>4500.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Input SGST</LEDGERNAME>
            <AMOUNT>4500.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Sundry Creditors</LEDGERNAME>
            <AMOUNT>-59000.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
        </VOUCHER>
      </COLLECTION>
    </DATA>
  </BODY>
</ENVELOPE>
""".strip()


@pytest.mark.asyncio
async def test_gstr1_vs_books_reconciliation_endpoint(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="GST Pilot Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    await async_client.post(
        f"/api/v1/erp/engagements/{engagement.id}/tally/trial-balance/import",
        json={"raw_xml": TRIAL_BALANCE_XML},
    )
    await async_client.post(
        f"/api/v1/erp/engagements/{engagement.id}/tally/vouchers/import",
        json={"raw_xml": SALES_VOUCHERS_XML},
    )

    response = await async_client.post(
        f"/api/v1/gst/engagements/{engagement.id}/reconcile/gstr1-vs-books",
        json={
            "portal_records": [
                {
                    "invoice_no": "INV-001",
                    "gstin": "27ABCDE1234F1Z5",
                    "taxable_value": 100000.0,
                    "tax_amount": 18000.0,
                    "period": "2026-04",
                },
                {
                    "invoice_no": "INV-002",
                    "gstin": "27MISSING1234F1Z5",
                    "taxable_value": 25000.0,
                    "tax_amount": 4500.0,
                    "period": "2026-04",
                },
            ]
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["summary"]["matched_count"] == 1
    assert payload["summary"]["mismatch_count"] == 1
    assert payload["mismatches"][0]["reason_codes"] == ["missing_in_books"]

    summary_response = await async_client.get(f"/api/v1/gst/engagements/{engagement.id}/reconciliations")
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert "gstr1_vs_books" in summary_payload["reconciliations"]


@pytest.mark.asyncio
async def test_gstr2b_vs_itc_flags_itc_variance(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="ITC Pilot Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    await async_client.post(
        f"/api/v1/erp/engagements/{engagement.id}/tally/vouchers/import",
        json={"raw_xml": PURCHASE_VOUCHERS_XML},
    )

    response = await async_client.post(
        f"/api/v1/gst/engagements/{engagement.id}/reconcile/gstr2b-vs-itc",
        json={
            "portal_records": [
                {
                    "invoice_no": "PUR-001",
                    "gstin": "27PQRSX1234L1Z9",
                    "taxable_value": 50000.0,
                    "tax_amount": 7000.0,
                    "period": "2026-04",
                }
            ]
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["summary"]["mismatch_count"] == 1
    assert payload["mismatches"][0]["reason_codes"] == ["excess_itc_claimed"]

    stored_transactions = list(await db_session.scalars(select(Transaction)))
    assert stored_transactions
