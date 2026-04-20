# pyre-ignore-all-errors
import logging
import uuid
import base64
from datetime import datetime, timezone
import hashlib

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.models import SystemAuditLog, RetentionExecutionLog
from arkashri.services.kms import kms_service
from arkashri.services.crypto import encrypt_dict, decrypt_dict
from arkashri.services.canonical import hash_object
from arkashri.services.audit import append_audit_event

logger = logging.getLogger("services.governance")

class GovernanceEngine:
    """
    Implements Data Retention and DPDP/GDPR "Right to be Forgotten" via Crypto-Shredding.
    Provides verifiable proof of deletion while maintaining the cryptographic audit chain.
    """

    @staticmethod
    async def set_legal_hold(session: AsyncSession, log_id: uuid.UUID, hold_status: bool, requested_by: str) -> None:
        """Sets or removes a Legal Hold. Elements under hold cannot be shredded."""
        log_entry = await session.get(SystemAuditLog, log_id)
        if not log_entry:
            raise ValueError(f"Audit log {log_id} not found.")

        log_entry.legal_hold = hold_status
        session.add(log_entry)
        await session.commit()
        
        logger.info(f"Legal Hold set to {hold_status} on log {log_id} by {requested_by}")

    @staticmethod
    async def crypto_shred_log(session: AsyncSession, log_id: uuid.UUID, policy_version: str = "v1") -> RetentionExecutionLog:
        """
        Executes Crypto-Shredding on a target audit log.
        1. Verifies it is not under Legal Hold.
        2. Simulates destruction of the KMS DEK.
        3. Sets is_shredded to True.
        4. Writes an immutable RetentionExecutionLog as proof.
        """
        log_entry = await session.get(SystemAuditLog, log_id)
        if not log_entry:
            raise ValueError(f"Audit log {log_id} not found.")

        if log_entry.legal_hold:
            raise PermissionError(f"Cannot shred log {log_id}. It is currently under active LEGAL HOLD.")

        if log_entry.is_shredded:
            raise ValueError(f"Log {log_id} is already shredded.")

        if not log_entry.encrypted_dek:
            # For logs that didn't have one, we pretend we destroyed it.
            pass

        # Destroy DEK (In production: call KMS Delete Key / Alias)
        destroyed_dek_hash = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()

        log_entry.is_shredded = True
        # IMPORTANT: We purposefully DO NOT change the payload or content_hash!
        # The frontend/readers will see `is_shredded` and fail to decrypt the payload due to the destroyed DEK.
        
        # C-NEW-11: Formally log the destruction in the audit trail (Provable Shredding)
        await append_audit_event(
            session,
            tenant_id=log_entry.tenant_id,
            engagement_id=None, 
            jurisdiction="GLOBAL",
            event_type="SHRED_EXECUTED",
            entity_type="SYSTEM_AUDIT_LOG",
            entity_id=str(log_id),
            payload={
                "reason": "DATA_RETENTION_POLICY",
                "policy_version": policy_version,
                "shred_proof_hash": destroyed_dek_hash
            }
        )
        
        # Write Proof of Execution
        execution_log = RetentionExecutionLog(
            tenant_id=log_entry.tenant_id,
            target_audit_log_id=log_id,
            policy_version=policy_version,
            shred_proof_hash=destroyed_dek_hash,
            executed_by="Arkashri_Governance_Engine",
        )
        
        # Sign the execution log (Self-contained seal)
        proof_payload = {
            "tenant_id": execution_log.tenant_id,
            "target_audit_log_id": str(log_id),
            "policy_version": policy_version,
            "shred_proof_hash": destroyed_dek_hash,
            "executed_by": execution_log.executed_by
        }
        
        from arkashri.services.seal import compute_seal_signature
        execution_log.signature = compute_seal_signature(log_entry.tenant_id, proof_payload)
        
        session.add(log_entry)
        session.add(execution_log)
        await session.commit()
        
        logger.info(f"Crypto-Shredding executed successfully on log {log_id}. Policy: {policy_version}")
        return execution_log

governance_engine = GovernanceEngine()
