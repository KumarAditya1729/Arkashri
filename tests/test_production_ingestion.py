# pyre-ignore-all-errors
from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from starlette.datastructures import Headers, UploadFile
from sqlalchemy import select

from arkashri.models import (
    Engagement,
    EngagementStatus,
    EngagementType,
    EvidenceRecord,
    FormulaRegistry,
    SignalType,
    StandardsFramework,
    Transaction,
    TransactionEvidenceMap,
    WeightEntry,
    WeightSet,
    RuleRegistry,
)
from arkashri.services.bank_ingestion import ingest_bank_records, parse_bank_csv
from arkashri.services.evidence import LocalStorageBackend, evidence_service
from arkashri.services.erp_adapter import normalize_batch
from arkashri.services.risk_engine import compute_risk


@pytest.fixture
def realistic_sap_record() -> dict:
    return {
        "BELNR": "5100001234",
        "BUDAT": "2026-01-31",
        "HKONT": "400000",
        "TXT50": "Revenue - Products",
        "DMBTR": "87430.50",
        "SHKZG": "H",
        "WAERS": "INR",
        "SGTXT": "January revenue posting",
        "NAME1": "Reliance Industries",
        "LIFNR": "V10023",
        "MWSKZ": "A1",
    }


@pytest.fixture
def bank_csv_payload() -> bytes:
    return (
        "date,description,reference,debit,credit,currency,account_number,account_name,entity\n"
        "2026-02-01,Vendor payment,UTR-1001,12500.00,,INR,1234567890,Operating Account,Acme Supplies\n"
        "2026-02-03,Customer receipt,UTR-1002,,42000.00,INR,1234567890,Operating Account,Northwind Retail\n"
    ).encode("utf-8")


def test_normalize_batch_preserves_external_record_values(realistic_sap_record: dict) -> None:
    normalized = normalize_batch("SAP_S4HANA", [realistic_sap_record])

    payload, payload_hash = normalized[0]
    assert payload["ref"] == realistic_sap_record["BELNR"]
    assert payload["date"] == realistic_sap_record["BUDAT"]
    assert payload["amount"] == 87430.5
    assert payload["entity"] == "Reliance Industries"
    assert payload["erp_system"] == "SAP_S4HANA"
    assert payload_hash


def test_normalize_batch_rejects_missing_required_fields(realistic_sap_record: dict) -> None:
    broken_record = {**realistic_sap_record}
    broken_record.pop("BELNR")

    normalized = normalize_batch("SAP_S4HANA", [broken_record])

    payload, _ = normalized[0]
    assert payload["risk_flags"] == ["PARSE_ERROR"]
    assert "Missing required field" in payload["error"]


@pytest.mark.asyncio
async def test_bank_csv_ingestion_requires_uploaded_rows(db_session, bank_csv_payload: bytes) -> None:
    records = parse_bank_csv(bank_csv_payload)
    result = await ingest_bank_records(
        db_session,
        tenant_id="tenant_ingestion",
        jurisdiction="IN",
        records=records,
        source="CSV_UPLOAD",
        default_currency="INR",
    )

    stored_transactions = list(await db_session.scalars(select(Transaction).order_by(Transaction.created_at.asc())))
    assert result.records_submitted == 2
    assert result.records_ingested == 2
    assert result.records_failed == 0
    assert len(stored_transactions) == 2
    assert stored_transactions[0].payload["source"] == "CSV_UPLOAD"
    assert stored_transactions[1].payload["type"] == "CREDIT"


@pytest.mark.asyncio
async def test_evidence_upload_and_linkage_use_real_file_content(db_session, tmp_path) -> None:
    evidence_service.backend = LocalStorageBackend(str(tmp_path))

    engagement = Engagement(
        tenant_id="tenant_evidence",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Real Client Pvt Ltd",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    transaction = Transaction(
        tenant_id="tenant_evidence",
        jurisdiction="IN",
        payload={"ref": "TXN-1001", "source": "CSV_UPLOAD"},
        payload_hash="txn-hash-1001",
    )
    db_session.add(transaction)
    await db_session.commit()
    await db_session.refresh(engagement)
    await db_session.refresh(transaction)

    upload = UploadFile(
        file=BytesIO(b"real evidence payload"),
        filename="invoice.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    file_path = await evidence_service.upload_evidence(engagement.tenant_id, upload)
    saved_bytes = await evidence_service.get_evidence_content(file_path)

    record = EvidenceRecord(
        engagement_id=engagement.id,
        tenant_id=engagement.tenant_id,
        evd_ref="EVD-001",
        file_name="invoice.pdf",
        file_path=file_path,
        evidence_type="Document",
        uploaded_by="auditor@example.com",
        ev_status="Pending Review",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    await evidence_service.link_evidence_to_transactions(
        db_session,
        record.id,
        [transaction.id],
        engagement.tenant_id,
        "auditor@example.com",
    )

    links = list(await db_session.scalars(select(TransactionEvidenceMap)))
    assert saved_bytes == b"real evidence payload"
    assert len(links) == 1
    assert links[0].transaction_id == transaction.id
    assert links[0].evidence_id == record.id


@pytest.mark.asyncio
async def test_risk_engine_flags_structured_high_value_mismatch(db_session) -> None:
    formula = FormulaRegistry(
        version=1,
        formula_text="FinalRisk = weighted_sum",
        formula_hash="f" * 64,
        component_caps={"DETERMINISTIC": 0.8, "ML": 0.2, "TREND": 0.0},
        is_active=True,
    )
    weight_set = WeightSet(version=1, weight_hash="w" * 64, is_active=True)
    db_session.add_all([formula, weight_set])
    await db_session.flush()
    db_session.add_all(
        [
            WeightEntry(weight_set_id=weight_set.id, signal_type=SignalType.DETERMINISTIC, signal_key="bank_amount_mismatch", weight=0.8),
            WeightEntry(weight_set_id=weight_set.id, signal_type=SignalType.ML, signal_key="fraud_anomaly", weight=0.2),
            RuleRegistry(
                rule_key="bank_amount_mismatch",
                version=1,
                name="Bank amount mismatch",
                description="Flags discrepancies between ledger and bank statement amounts.",
                expression={"field": "amount_delta", "op": "gte", "value": 10000},
                signal_value=1.0,
                severity_floor=80.0,
                is_active=True,
            ),
        ]
    )
    await db_session.commit()

    with patch("arkashri.services.risk_engine.cache_get", new_callable=AsyncMock) as cache_get, patch(
        "arkashri.services.risk_engine.cache_set",
        new_callable=AsyncMock,
    ):
        cache_get.return_value = None
        result = await compute_risk(
            db_session,
            payload={"amount_delta": 15000},
            ml_signals=[{"key": "fraud_anomaly", "value": 0.4}],
            trend_signals=[],
            model_stability=0.95,
        )

    assert result.final_risk >= 80.0
    assert any(component.signal_key == "bank_amount_mismatch" for component in result.components)
