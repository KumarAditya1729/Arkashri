import pytest

from arkashri.models import Engagement, EngagementStatus, EngagementType, EvidenceRecord, StandardsFramework
from arkashri.services import crypto
from arkashri.services.crypto import decrypt_sensitive_value, encrypt_sensitive_value


def test_sensitive_value_encryption_is_tenant_bound(monkeypatch) -> None:
    monkeypatch.setattr(crypto.settings, "field_data_encryption_key", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    encrypted = encrypt_sensitive_value("27ABCDE1234F1Z5", tenant_id="tenant-a", field_name="gstin")

    assert encrypted["ciphertext"]
    assert encrypted["last4"] == "4F1Z5"[-4:]
    assert "27ABCDE1234F1Z5" not in encrypted["ciphertext"]
    assert decrypt_sensitive_value(encrypted, tenant_id="tenant-a", field_name="gstin") == "27ABCDE1234F1Z5"

    with pytest.raises(Exception):
        decrypt_sensitive_value(encrypted, tenant_id="tenant-b", field_name="gstin")


@pytest.mark.asyncio
async def test_evidence_routes_enforce_tenant_ownership(async_client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    engagement = Engagement(
        tenant_id="tenant-a",
        jurisdiction="IN",
        standards_framework=StandardsFramework.ICAI_SA,
        client_name="Tenant Guard Private Limited",
        engagement_type=EngagementType.STATUTORY_AUDIT,
        status=EngagementStatus.ACCEPTED,
        independence_cleared=True,
        kyc_cleared=True,
    )
    db_session.add(engagement)
    await db_session.commit()
    await db_session.refresh(engagement)

    evidence = EvidenceRecord(
        engagement_id=engagement.id,
        tenant_id="tenant-a",
        evd_ref="EVD-001",
        file_name="bank.pdf",
        file_path="/tmp/bank.pdf",
        evidence_type="Document",
        uploaded_by="tester",
    )
    db_session.add(evidence)
    await db_session.commit()
    await db_session.refresh(evidence)

    cross_tenant_list = await async_client.get(
        f"/api/v1/engagements/{engagement.id}/evidence",
        headers={"X-Arkashri-Tenant": "tenant-b"},
    )
    assert cross_tenant_list.status_code == 403

    cross_tenant_download = await async_client.get(
        f"/api/v1/engagements/{engagement.id}/evidence/{evidence.id}/download-url",
        headers={"X-Arkashri-Tenant": "tenant-b"},
    )
    assert cross_tenant_download.status_code == 404
