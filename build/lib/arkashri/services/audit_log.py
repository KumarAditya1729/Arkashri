# pyre-ignore-all-errors
import structlog
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from arkashri.models import SystemAuditLog

logger = structlog.get_logger("services.audit_log")

from arkashri.services.evidence import evidence_service

async def log_system_event(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: uuid.UUID | None = None,
    user_email: str | None = None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    status: str = "SUCCESS",
    extra_metadata: dict[str, Any] | None = None,
    request: Any | None = None, # FastAPI Request object
):
    """
    Upgraded: Creates and cryptographically signs an entry in the system_audit_log table.
    Ensures SOC 2 / ISO 27001 proof-of-enforcement compliance.
    """
    await evidence_service.emit_signed_audit_event(
        session=db,
        request=request,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        tenant_id=tenant_id,
        user_id=user_id,
        user_email=user_email,
        status=status,
        metadata=extra_metadata
    )
    # The evidence_service handles session.add and session.commit/flush
