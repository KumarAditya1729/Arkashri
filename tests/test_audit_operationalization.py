# pyre-ignore-all-errors
from __future__ import annotations

import pytest
from sqlalchemy import select

from arkashri.models import (
    Engagement,
    EngagementStatus,
    EngagementType,
    EvidenceRecord,
    StandardsFramework,
    Transaction,
    TransactionEvidenceMap,
)
from arkashri.services.evidence import evidence_service
from arkashri.services.scorecard import compute_scorecard


@pytest.mark.asyncio
async def test_evidence_transaction_linkage(db_session) -> None:
    engagement = Engagement(
        tenant_id="test-tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Integration Client",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    txn = Transaction(
        tenant_id="test-tenant",
        jurisdiction="IN",
        payload={"ref": "TXN001", "amount": 100.0, "source": "CSV_UPLOAD"},
        payload_hash="hash001",
    )
    db_session.add(txn)
    await db_session.commit()
    await db_session.refresh(txn)

    evidence = EvidenceRecord(
        engagement_id=engagement.id,
        tenant_id="test-tenant",
        evd_ref="EVD-001",
        file_name="invoice.pdf",
        file_path="uploads/test.pdf",
        evidence_type="Document",
        uploaded_by="auditor@example.com",
        ev_status="Pending Review",
    )
    db_session.add(evidence)
    await db_session.commit()
    await db_session.refresh(evidence)

    await evidence_service.link_evidence_to_transactions(
        db_session,
        evidence.id,
        [txn.id],
        "test-tenant",
        "auditor@example.com",
    )

    stmt = select(TransactionEvidenceMap).where(TransactionEvidenceMap.transaction_id == txn.id)
    mapping = await db_session.scalar(stmt)
    assert mapping is not None
    assert mapping.evidence_id == evidence.id


@pytest.mark.asyncio
async def test_scorecard_uses_real_evidence_coverage(db_session) -> None:
    engagement = Engagement(
        tenant_id="test-tenant",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Scorecard Client",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    txn1 = Transaction(
        tenant_id="test-tenant",
        jurisdiction="IN",
        payload={"ref": "T1", "source": "ERP_API"},
        payload_hash="h1",
    )
    txn2 = Transaction(
        tenant_id="test-tenant",
        jurisdiction="IN",
        payload={"ref": "T2", "source": "CSV_UPLOAD"},
        payload_hash="h2",
    )
    db_session.add_all([txn1, txn2])
    await db_session.commit()
    await db_session.refresh(txn1)
    await db_session.refresh(txn2)

    evidence = EvidenceRecord(
        engagement_id=engagement.id,
        tenant_id="test-tenant",
        evd_ref="EVD-002",
        file_name="bank.csv",
        file_path="uploads/bank.csv",
        evidence_type="BankStatement",
        uploaded_by="auditor@example.com",
        ev_status="Verified",
    )
    db_session.add(evidence)
    await db_session.commit()
    await db_session.refresh(evidence)

    await evidence_service.link_evidence_to_transactions(
        db_session,
        evidence.id,
        [txn1.id],
        "test-tenant",
        "auditor@example.com",
    )

    scorecard = await compute_scorecard(db_session, tenant_id="test-tenant", jurisdiction="IN")
    assert scorecard.evidence_coverage_rate == 0.5
