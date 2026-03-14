# pyre-ignore-all-errors
import structlog
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from arkashri.models import SystemAuditLog

logger = structlog.get_logger("services.audit_log")

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
    Creates a new entry in the system_audit_log table.
    Captures request context (IP, User-Agent, Request-ID) automatically if request is provided.
    """
    request_id = None
    ip_address = None
    user_agent = None
    
    if request:
        request_id = request.headers.get("X-Request-ID")
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")

    event = SystemAuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        user_email=user_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        extra_metadata=extra_metadata,
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    
    db.add(event)
    try:
        await db.commit()
        logger.info("system_event_logged", action=action, tenant_id=tenant_id, user=user_email)
    except Exception as e:
        logger.error("system_event_logging_failed", error=str(e))
        await db.rollback()
