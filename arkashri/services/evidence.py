# pyre-ignore-all-errors
"""
services/evidence.py — Evidence storage, signing, and transaction linkage.

Two responsibilities:
  1. InternalEvidenceService — cryptographic signing of SystemAuditLog entries.
  2. EvidenceStorageService  — file storage (local or S3), retrieval, deletion,
                               and transaction ↔ evidence linkage.

The module-level ``evidence_service`` singleton exposes BOTH sets of methods so
existing callers (routers, tests) keep working unchanged.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.models import SystemAuditLog, TransactionEvidenceMap
from arkashri.services.seal import compute_seal_hash, compute_seal_signature
from arkashri.services.object_storage import object_storage_service

logger = logging.getLogger("services.evidence")


class LocalStorageBackend:
    """Backward-compatible local evidence backend used by older tests/callers."""

    def __init__(self, base_dir: str):
        from arkashri.services.object_storage import LocalObjectStorage

        self._storage = LocalObjectStorage(base_dir)

    async def save(self, tenant_id: str, file: UploadFile) -> str:
        content = await file.read()
        stored = await self._storage.save_bytes(
            key=f"{tenant_id}/{uuid.uuid4()}_{file.filename or 'upload'}",
            content=content,
            content_type=file.content_type,
        )
        return stored.uri

    async def read(self, file_path: str) -> bytes:
        return await self._storage.read_bytes(file_path)

    async def delete(self, file_path: str) -> None:
        await self._storage.delete(file_path)


# ─── Combined evidence service ────────────────────────────────────────────────

class EvidenceService:
    """
    Combined service exposing:
      - File storage operations (upload_evidence, get_evidence_content, delete_evidence)
      - Transaction linkage   (link_evidence_to_transactions)
      - Audit log signing     (sign_audit_log, emit_signed_audit_event)  ← previously InternalEvidenceService
    """

    def __init__(self):
        self.storage = object_storage_service
        self.backend = None

    # ── Storage operations ────────────────────────────────────────────────────

    async def upload_evidence(self, tenant_id: str, file: UploadFile) -> str:
        """
        Persist an uploaded file and return its storage path.
        Called by: routers/evidence.py, routers/rag.py.
        """
        if self.backend is not None:
            return await self.backend.save(tenant_id, file)

        content = await file.read()
        stored = await self.storage.save_bytes(
            tenant_id=tenant_id,
            category="evidence",
            filename=file.filename or "upload",
            content=content,
            content_type=file.content_type,
        )
        logger.info("evidence_saved uri=%s size=%s", stored.uri, len(content))
        return stored.uri

    async def get_evidence_content(self, file_path: str) -> bytes:
        """Retrieve raw bytes for an evidence file (for RAG ingestion, etc.)."""
        if self.backend is not None:
            return await self.backend.read(file_path)
        return await self.storage.read_bytes(file_path)

    async def delete_evidence(self, file_path: str) -> None:
        """Remove an evidence file from storage."""
        if self.backend is not None:
            await self.backend.delete(file_path)
            return
        await self.storage.delete(file_path)

    async def get_evidence_download_url(self, file_path: str, *, expires_in: int = 3600) -> str:
        return await self.storage.presigned_url(file_path, expires_in=expires_in)

    # ── Transaction linkage ───────────────────────────────────────────────────

    async def link_evidence_to_transactions(
        self,
        session: AsyncSession,
        evidence_id: uuid.UUID,
        transaction_ids: List[uuid.UUID],
        tenant_id: str,
        linked_by: str,
    ) -> None:
        """
        Create TransactionEvidenceMap rows linking evidence to one or more transactions.
        Idempotent: skips rows that already exist.
        """
        # Fetch existing links to avoid duplicates
        existing = set(
            await session.scalars(
                select(TransactionEvidenceMap.transaction_id).where(
                    TransactionEvidenceMap.evidence_id == evidence_id
                )
            )
        )

        new_rows: list[TransactionEvidenceMap] = []
        for tx_id in transaction_ids:
            if tx_id not in existing:
                new_rows.append(
                    TransactionEvidenceMap(
                        evidence_id=evidence_id,
                        transaction_id=tx_id,
                        tenant_id=tenant_id,
                        linked_by=linked_by,
                    )
                )

        if new_rows:
            session.add_all(new_rows)
            await session.commit()
            logger.info(
                "evidence_linked evidence_id=%s linked_count=%s tenant_id=%s",
                evidence_id,
                len(new_rows),
                tenant_id,
            )

    # ── Audit log signing (formerly InternalEvidenceService) ─────────────────

    @staticmethod
    def _canonical_log_representation(log_entry: Dict[str, Any]) -> dict:
        """
        Create a deterministic dictionary for hashing.
        Excludes the fields that will be updated (hash, signature).
        """
        core_fields = [
            "tenant_id", "user_id", "action", "resource_type",
            "resource_id", "status", "extra_metadata", "request_id",
            "ip_address", "created_at",
        ]
        canonical: dict = {}
        for field in core_fields:
            val = log_entry.get(field)
            if isinstance(val, datetime):
                val = val.replace(tzinfo=timezone.utc).isoformat()
            canonical[field] = val
        return canonical

    async def sign_audit_log(
        self,
        session: AsyncSession,
        log_id: Any,
    ) -> None:
        """
        Retrieves a log entry, computes its hash and ECDSA signature, and updates it.
        Provides the 'Audit Proof' required for SOC 2.
        """
        log = await session.get(SystemAuditLog, log_id)
        if not log:
            return

        payload = self._canonical_log_representation({
            "tenant_id":      log.tenant_id,
            "user_id":        str(log.user_id) if log.user_id else None,
            "action":         log.action,
            "resource_type":  log.resource_type,
            "resource_id":    log.resource_id,
            "status":         log.status,
            "extra_metadata": log.extra_metadata,
            "request_id":     log.request_id,
            "ip_address":     log.ip_address,
            "created_at":     log.created_at,
        })

        log.content_hash = compute_seal_hash(payload)
        log.signature    = compute_seal_signature(log.tenant_id, payload)

        session.add(log)
        await session.commit()

        logger.info(f"Evidence sealed for log {log_id}. signature_v1={log.signature[:8]}...")

    async def emit_signed_audit_event(
        self,
        session: AsyncSession,
        request: Optional[Request],
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        tenant_id: str = "default",
        user_id: Optional[uuid.UUID] = None,
        user_email: Optional[str] = None,
        status: str = "SUCCESS",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> uuid.UUID:
        """
        Creates, hashes, signs, and persists a SystemAuditLog entry.
        Provides a tamper-evident record of administrative and sensitive actions.
        """
        correlation_id = getattr(request.state, "correlation_id", None) if request else None
        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("User-Agent") if request else None

        log = SystemAuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            user_email=user_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            extra_metadata=metadata,
            request_id=correlation_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        log.created_at = datetime.now(timezone.utc)

        session.add(log)
        await session.flush()  # Populate ID

        payload = self._canonical_log_representation({
            "tenant_id":      log.tenant_id,
            "user_id":        str(log.user_id) if log.user_id else None,
            "action":         log.action,
            "resource_type":  log.resource_type,
            "resource_id":    log.resource_id,
            "status":         log.status,
            "extra_metadata": log.extra_metadata,
            "request_id":     log.request_id,
            "ip_address":     log.ip_address,
            "created_at":     log.created_at,
        })

        log.content_hash = compute_seal_hash(payload)
        log.signature    = compute_seal_signature(log.tenant_id, payload)

        logger.info(
            f"Signed Audit Emitted: {action} on {resource_type} ({status}). "
            f"Trace: {correlation_id}"
        )
        return log.id


# ── Backward-compatible aliases ───────────────────────────────────────────────

# Legacy callers that imported InternalEvidenceService directly
InternalEvidenceService = EvidenceService

# Global singleton — all routers and tests import this
evidence_service = EvidenceService()
