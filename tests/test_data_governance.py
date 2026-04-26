import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import SystemAuditLog
from arkashri.services.governance import governance_engine
from arkashri.services.seal import verify_seal_signature

@pytest.mark.asyncio
async def test_legal_hold_blocks_shredding(test_session: AsyncSession):
    # Setup Log
    tenant_id = "tenant-007"
    log = SystemAuditLog(
        tenant_id=tenant_id,
        action="TEST_PII_WRITE",
        resource_type="USER",
        legal_hold=True,
        encrypted_dek="kms:encrypted:abc",
        is_shredded=False
    )
    test_session.add(log)
    await test_session.commit()
    
    # Attempt Shredding
    with pytest.raises(PermissionError) as exc_info:
        await governance_engine.crypto_shred_log(test_session, log.id)
    
    assert "LEGAL HOLD" in str(exc_info.value)
    
    # Remove hold
    await governance_engine.set_legal_hold(test_session, log.id, False, "Admin")
    
    # Should succeed now
    execution_proof = await governance_engine.crypto_shred_log(test_session, log.id)
    assert execution_proof is not None
    
    # Assert DB State
    updated_log = await test_session.get(SystemAuditLog, log.id)
    assert updated_log.is_shredded

@pytest.mark.asyncio
async def test_crypto_shredding_proof_signature(test_session: AsyncSession):
    tenant_id = "tenant-008"
    log = SystemAuditLog(
        tenant_id=tenant_id,
        action="TEST_GDPR_DELETE",
        resource_type="USER",
        encrypted_dek="kms:encrypted:xyz",
    )
    test_session.add(log)
    await test_session.commit()
    
    proof = await governance_engine.crypto_shred_log(test_session, log.id)
    
    # Verify the Execution Proof
    payload = {
        "tenant_id": proof.tenant_id,
        "target_audit_log_id": str(log.id),
        "policy_version": "v1",
        "shred_proof_hash": proof.shred_proof_hash,
        "executed_by": "Arkashri_Governance_Engine"
    }
    
    is_valid = verify_seal_signature(tenant_id, payload, proof.signature)
    assert is_valid
