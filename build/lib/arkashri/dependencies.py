# pyre-ignore-all-errors
from __future__ import annotations

import uuid
from typing import Any
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from slowapi import Limiter
from slowapi.util import get_remote_address

from arkashri.config import get_settings
from arkashri.db import get_session
from arkashri.models import (
    ClientRole,
    AuditEvent,
    Transaction,
    Decision,
    IdempotencyRecord,
    AuditRun,
    ApprovalRequest,
    User,
)
from arkashri.services.auth_sessions import load_active_session_from_claims
from arkashri.services.security import AuthContext, build_system_context, resolve_api_client
from arkashri.services.jwt_service import decode_token
from arkashri.services.audit import append_audit_event
from arkashri.services.realtime import realtime_hub

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)

def serialize_platform_user(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "sub": str(user.id),
        "user_id": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "tenant_id": user.tenant_id,
        "full_name": user.full_name,
        "initials": user.initials,
    }


async def load_active_user_from_claims(session: AsyncSession, claims: dict[str, Any]) -> User:
    await load_active_session_from_claims(session, claims)

    user_id = claims.get("user_id") or claims.get("sub")
    tenant_id = claims.get("tenant_id")

    if not user_id or not tenant_id:
        raise HTTPException(status_code=401, detail="Token is missing required user claims.")

    try:
        user_uuid = uuid.UUID(str(user_id))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Token user identifier is invalid.") from exc

    user = await session.scalar(
        select(User).where(
            User.id == user_uuid,
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise HTTPException(status_code=401, detail="User account not found or deactivated.")

    return user


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get current user from session or JWT token"""
    if 'session' in request.scope:
        user = request.session.get('user')
        if user:
            return user

    auth_header = request.headers.get('authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        claims = decode_token(token)
        user = await load_active_user_from_claims(session, claims)
        return serialize_platform_user(user)

    raise HTTPException(
        status_code=401, 
        detail="Not authenticated. Valid JWT Bearer token required."
    )

SYSTEM_TENANT = "_system"
SYSTEM_JURISDICTION = "GLOBAL"
DEFAULT_APPROVAL_ESCALATION_MINUTES = 120

AGENT_CATALOG = [
    {"agent_key": "ingest_guard", "name": "Ingestion Guard", "domain": "Ingestion Integrity"},
    {"agent_key": "schema_sentinel", "name": "Schema Sentinel", "domain": "Schema Governance"},
    {"agent_key": "rule_linter", "name": "Rule Linter", "domain": "Rule Validation"},
    {"agent_key": "weight_governor", "name": "Weight Governor", "domain": "Weight Compliance"},
    {"agent_key": "model_attestor", "name": "Model Attestor", "domain": "ML Artifact Control"},
    {"agent_key": "drift_watch", "name": "Drift Watch", "domain": "Drift Monitoring"},
    {"agent_key": "coverage_guard", "name": "Coverage Guard", "domain": "Coverage Reconciliation"},
    {"agent_key": "exception_triage", "name": "Exception Triage", "domain": "Exception Workflow"},
    {"agent_key": "override_auditor", "name": "Override Auditor", "domain": "Override Governance"},
    {"agent_key": "ledger_anchor", "name": "Ledger Anchor", "domain": "Blockchain Anchoring"},
    {"agent_key": "forensic_replay", "name": "Forensic Replay", "domain": "Reproducibility"},
    {"agent_key": "report_assembler", "name": "Report Assembler", "domain": "Automated Reporting"},
    {"agent_key": "jurisdiction_mapper", "name": "Jurisdiction Mapper", "domain": "Compliance Mapping"},
    {"agent_key": "incident_notary", "name": "Incident Notary", "domain": "Security Disclosure"},
]


def _channel_key(tenant_id: str, jurisdiction: str) -> str:
    return f"{tenant_id}:{jurisdiction}"


async def _append_and_publish_audit(
    session: AsyncSession,
    *,
    tenant_id: str,
    jurisdiction: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
) -> AuditEvent:
    event = await append_audit_event(
        session,
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )
    realtime_hub.publish(
        _channel_key(tenant_id, jurisdiction),
        {
            "event_id": event.id,
            "event_type": event.event_type,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "event_hash": event.event_hash,
            "payload": event.payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return event


async def _audit_registry_change(
    session: AsyncSession,
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
) -> None:
    await _append_and_publish_audit(
        session,
        tenant_id=SYSTEM_TENANT,
        jurisdiction=SYSTEM_JURISDICTION,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )


async def _coverage_counts(session: AsyncSession, tenant_id: str, jurisdiction: str) -> tuple[int, int, float]:
    transactions_received = int(
        await session.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.tenant_id == tenant_id,
                Transaction.jurisdiction == jurisdiction,
            )
        )
        or 0
    )
    decisions_computed = int(
        await session.scalar(
            select(func.count(Decision.id))
            .join(Transaction, Decision.transaction_id == Transaction.id)
            .where(Transaction.tenant_id == tenant_id, Transaction.jurisdiction == jurisdiction)
        )
        or 0
    )
    coverage_rate = round(decisions_computed / transactions_received, 6) if transactions_received else 0.0
    return transactions_received, decisions_computed, coverage_rate


# Map JWT user roles → ClientRole for permission checks
# Handles both uppercase (UserRole enum values) and lowercase (frontend-assigned roles)
_JWT_ROLE_MAP: dict[str, ClientRole] = {
    # Uppercase (canonical backend UserRole enum values)
    "ADMIN":     ClientRole.ADMIN,
    "OPERATOR":  ClientRole.OPERATOR,
    "REVIEWER":  ClientRole.REVIEWER,
    "READ_ONLY": ClientRole.READ_ONLY,
    # Lowercase (frontend-registered user roles)
    "admin":     ClientRole.ADMIN,
    "operator":  ClientRole.OPERATOR,
    "reviewer":  ClientRole.REVIEWER,
    "read_only": ClientRole.READ_ONLY,
    # Aliases used by the register page
    "auditor":   ClientRole.OPERATOR,   # Auditors get full operator rights
    "ca":        ClientRole.OPERATOR,
    "partner":   ClientRole.ADMIN,
}



def require_api_client(allowed_roles: set[ClientRole] | None = None):
    async def _dependency(
        request: Request,
        session: AsyncSession = Depends(get_session),
        authorization: str | None = Header(default=None, alias="Authorization"),
        api_key: str | None = Header(default=None, alias="X-Arkashri-Key"),
        _tenant_header: str = Header(default="default_tenant", alias="X-Arkashri-Tenant"),
    ) -> AuthContext:
        # Enforce Postgres RLS dynamically on the current connection context
        # await session.execute(text("SELECT set_config('app.current_tenant', :tenant_id, true)"), {"tenant_id": _tenant_header})

        if not settings.auth_enforced:
            return build_system_context(tenant_id=_tenant_header)

        # ── Path 1: JWT Bearer token (preferred) ─────────────────────────────
        if authorization and authorization.startswith("Bearer "):
            token = authorization.removeprefix("Bearer ").strip()
            claims = decode_token(token)          # raises HTTP 401 if invalid/expired
            user = await load_active_user_from_claims(session, claims)
            role_str = user.role.value
            client_role = _JWT_ROLE_MAP.get(role_str, ClientRole.READ_ONLY)
            tenant_id = user.tenant_id

            if allowed_roles and client_role not in allowed_roles:
                raise HTTPException(status_code=403, detail="Insufficient role privileges")

            return AuthContext(
                client_id=str(user.id),
                client_name=user.full_name,
                role=client_role,
                tenant_id=tenant_id,
            )

        # ── Path 2: Legacy X-Arkashri-Key (API key) ───────────────────────────
        if api_key:
            client = await resolve_api_client(session, api_key)
            if client is None:
                raise HTTPException(status_code=401, detail="Invalid API key")
            tenant_id = getattr(client, "tenant_id", _tenant_header)
            auth_context = AuthContext(
                client_id=client.id,
                client_name=client.name,
                role=client.role,
                tenant_id=tenant_id,
            )
            if allowed_roles and client.role not in allowed_roles:
                raise HTTPException(status_code=403, detail="Insufficient role privileges")
            return auth_context

        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide 'Authorization: Bearer <token>' or 'X-Arkashri-Key' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _dependency


def require_user(request: Request) -> dict[str, Any]:
    if not settings.auth_enforced:
        return {"sub": "system", "email": "system@arkashri.local", "name": "System Administrator"}

    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated via Enterprise OIDC")
    return user


async def _fetch_idempotency_record(
    session: AsyncSession,
    *,
    tenant_id: str,
    jurisdiction: str,
    idempotency_key: str,
) -> IdempotencyRecord | None:
    return await session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == tenant_id,
            IdempotencyRecord.jurisdiction == jurisdiction,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )


async def _load_run_with_steps(session: AsyncSession, run_id: uuid.UUID) -> AuditRun | None:
    stmt = (
        select(AuditRun)
        .options(joinedload(AuditRun.steps))
        .where(AuditRun.id == run_id)
    )
    result = await session.execute(stmt)
    return result.unique().scalars().first()


async def _load_approval_with_actions(session: AsyncSession, request_id: uuid.UUID) -> ApprovalRequest | None:
    stmt = (
        select(ApprovalRequest)
        .options(joinedload(ApprovalRequest.actions))
        .where(ApprovalRequest.id == request_id)
    )
    result = await session.execute(stmt)
    return result.unique().scalars().first()
