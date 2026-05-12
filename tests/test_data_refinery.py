from __future__ import annotations

import zipfile
from io import BytesIO

import pytest
from sqlalchemy import select

from arkashri.models import AuditEvent, Engagement, EngagementStatus, EngagementType, StandardsFramework, Transaction
from arkashri.services.data_refinery import MAX_UPLOAD_BYTES, build_excel_refinery_preview, build_refinery_preview


def _csv_bytes() -> bytes:
    return (
        "Txn Date,Narration,Voucher No,Debit,Credit,Ledger Name,Party GSTIN\n"
        "2026-04-01,Sales receipt from customer,RCPT-001,,150000.00,HDFC Bank,27ABCDE1234F1Z5\n"
        "2026-04-04,Manual cash adjustment,JV-ROUND,100000.00,,Cash Account,\n"
    ).encode("utf-8")


def _xlsx_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>""")
        zf.writestr("xl/workbook.xml", """<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sales" sheetId="1" r:id="rId1"/><sheet name="Bank" sheetId="2" r:id="rId2"/></sheets></workbook>""")
        zf.writestr("xl/_rels/workbook.xml.rels", """<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>""")
        zf.writestr("xl/worksheets/sheet1.xml", """<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Txn Date</t></is></c><c r="B1" t="inlineStr"><is><t>Narration</t></is></c><c r="C1" t="inlineStr"><is><t>Voucher No</t></is></c><c r="D1" t="inlineStr"><is><t>Credit</t></is></c><c r="E1" t="inlineStr"><is><t>Ledger Name</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>2026-04-01</t></is></c><c r="B2" t="inlineStr"><is><t>Sales receipt</t></is></c><c r="C2" t="inlineStr"><is><t>S-1</t></is></c><c r="D2"><v>100000</v></c><c r="E2" t="inlineStr"><is><t>Sales</t></is></c></row></sheetData></worksheet>""")
        zf.writestr("xl/worksheets/sheet2.xml", """<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Txn Date</t></is></c><c r="B1" t="inlineStr"><is><t>Narration</t></is></c><c r="C1" t="inlineStr"><is><t>Voucher No</t></is></c><c r="D1" t="inlineStr"><is><t>Debit</t></is></c><c r="E1" t="inlineStr"><is><t>Ledger Name</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>2026-04-02</t></is></c><c r="B2" t="inlineStr"><is><t>Bank payment</t></is></c><c r="C2" t="inlineStr"><is><t>B-1</t></is></c><c r="D2"><v>50000</v></c><c r="E2" t="inlineStr"><is><t>HDFC Bank</t></is></c></row></sheetData></worksheet>""")
    return buffer.getvalue()


def test_data_refinery_preview_maps_and_flags_raw_csv() -> None:
    preview = build_refinery_preview(_csv_bytes(), source_type="books_ledger")

    assert preview["total_rows"] == 2
    assert preview["audit_ready_rows"] == 2
    assert preview["can_ingest"] is True
    assert len(preview["source_file_hash"]) == 64
    assert preview["suggested_mapping"]["date"] == "Txn Date"
    assert preview["suggested_mapping"]["description"] == "Narration"
    assert preview["suggested_mapping"]["reference"] == "Voucher No"
    assert preview["category_breakdown"]["cash_and_bank"] == 2
    assert preview["risk_flag_breakdown"]["ROUND_AMOUNT"] == 2
    assert preview["risk_flag_breakdown"]["SENSITIVE_NARRATION"] == 1
    assert preview["normalized_preview"][0]["type"] == "CREDIT"
    assert preview["normalized_preview"][1]["type"] == "DEBIT"


def test_data_refinery_preview_blocks_missing_date_mapping() -> None:
    payload = (
        "Narration,Voucher No,Amount\n"
        "Sales receipt,RCPT-001,150000.00\n"
    ).encode("utf-8")

    preview = build_refinery_preview(payload, source_type="sales_register")

    assert preview["can_ingest"] is False
    assert any(issue["field"] == "date" and issue["severity"] == "CRITICAL" for issue in preview["issues"])


def test_excel_multi_sheet_preview_maps_workbook() -> None:
    preview = build_excel_refinery_preview(_xlsx_bytes(), source_type="books_ledger")

    assert preview["sheet_count"] == 2
    assert preview["total_rows"] == 2
    assert preview["audit_ready_rows"] == 2
    assert len(preview["source_file_hash"]) == 64
    assert {sheet["sheet_name"] for sheet in preview["sheets"]} == {"Sales", "Bank"}
    assert all("readiness_score" in sheet for sheet in preview["sheets"])
    assert all("can_ingest" in sheet for sheet in preview["sheets"])


@pytest.mark.asyncio
async def test_data_refinery_ingests_audit_ready_transactions(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Raw Data Client Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    preview = await async_client.post(
        "/api/v1/data-refinery/preview",
        files={"file": ("raw-ledger.csv", _csv_bytes(), "text/csv")},
        data={"source_type": "books_ledger"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_ingest"] is True

    ingest = await async_client.post(
        f"/api/v1/data-refinery/engagements/{engagement.id}/ingest-csv",
        files={"file": ("raw-ledger.csv", _csv_bytes(), "text/csv")},
        data={"source_type": "books_ledger"},
    )
    assert ingest.status_code == 201, ingest.text
    body = ingest.json()
    assert body["batch_id"]
    assert len(body["source_file_hash"]) == 64
    assert body["records_submitted"] == 2
    assert body["records_ingested"] == 2
    assert body["category_breakdown"]["cash_and_bank"] == 2

    transactions = list(await db_session.scalars(select(Transaction).order_by(Transaction.created_at.asc())))
    assert len(transactions) == 2
    assert transactions[0].payload["engagement_id"] == str(engagement.id)
    assert transactions[0].payload["source"] == "DATA_REFINERY"
    assert transactions[0].payload["batch_id"] == body["batch_id"]
    assert transactions[0].payload["source_file_hash"] == body["source_file_hash"]
    assert transactions[0].payload["mapped_category"] == "cash_and_bank"
    event = await db_session.scalar(select(AuditEvent).where(AuditEvent.event_type == "DATA_REFINERY_INGESTED"))
    assert event is not None
    assert event.entity_id == body["batch_id"]
    assert event.payload["records_ingested"] == 2

    rerun = await async_client.post(
        f"/api/v1/data-refinery/engagements/{engagement.id}/ingest-csv",
        files={"file": ("raw-ledger.csv", _csv_bytes(), "text/csv")},
        data={"source_type": "books_ledger"},
    )
    assert rerun.status_code == 201, rerun.text
    assert rerun.json()["records_ingested"] == 0
    assert set(rerun.json()["duplicate_refs"]) == {"RCPT-001", "JV-ROUND"}


@pytest.mark.asyncio
async def test_data_refinery_rejects_sealed_engagement(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    engagement = Engagement(
        tenant_id="default_tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Sealed Client Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.SEALED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    response = await async_client.post(
        f"/api/v1/data-refinery/engagements/{engagement.id}/ingest-csv",
        files={"file": ("raw-ledger.csv", _csv_bytes(), "text/csv")},
        data={"source_type": "books_ledger"},
    )

    assert response.status_code == 409
    assert "sealed engagement" in response.text


def test_data_refinery_rejects_large_upload() -> None:
    huge = b"date,amount\n" + (b"1" * MAX_UPLOAD_BYTES)

    with pytest.raises(ValueError, match="100 MB"):
        build_refinery_preview(huge, source_type="books_ledger")


@pytest.mark.asyncio
async def test_pdf_bank_statement_ocr_gate(async_client, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)
    response = await async_client.post(
        "/api/v1/data-refinery/preview-bank-pdf",
        files={"file": ("bank.pdf", b"%PDF-1.4\n%test", "application/pdf")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] in {"OCR_PROVIDER_REQUIRED", "OCR_READY_FOR_EXTRACTION"}
    assert response.json()["can_ingest"] is False
