# pyre-ignore-all-errors
from __future__ import annotations

import datetime
import secrets
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.config import get_settings
from arkashri.models import PlatformSession, User
from arkashri.services.canonical import sha256_hex
from arkashri.services.jwt_service import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_access_token_expires_in_seconds,
)

_REFRESH_REUSE_GRACE_SECONDS = 5


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_in: int


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _refresh_expiry_delta() -> datetime.timedelta:
    return datetime.timedelta(days=get_settings().refresh_token_expiry_days)


def _token_hash(token: str) -> str:
    return sha256_hex(token)


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return first_hop

    return request.client.host if request.client else None


def _user_agent(request: Request | None) -> str | None:
    if request is None:
        return None

    agent = request.headers.get("user-agent")
    return agent[:2048] if agent else None


def _is_same_client(session_record: PlatformSession, request: Request | None) -> bool:
    request_ip = _client_ip(request)
    request_agent = _user_agent(request)

    if session_record.client_ip and request_ip and session_record.client_ip != request_ip:
        return False
    if session_record.user_agent and request_agent and session_record.user_agent != request_agent:
        return False

    return True


def _within_reuse_grace_window(last_used_at: datetime.datetime | None, now: datetime.datetime) -> bool:
    if last_used_at is None:
        return False

    return (now - last_used_at) <= datetime.timedelta(seconds=_REFRESH_REUSE_GRACE_SECONDS)


async def _issue_session_tokens(
    db: AsyncSession,
    *,
    user: User,
    request: Request | None,
    session_record: PlatformSession | None = None,
    family_id: uuid.UUID | None = None,
) -> tuple[PlatformSession, TokenBundle]:
    now = _utcnow()
    if session_record is not None:
        token_family_id = family_id or session_record.family_id
    else:
        token_family_id = family_id or uuid.uuid4()
    refresh_expires_at = now + _refresh_expiry_delta()

    if session_record is None:
        session_record = PlatformSession(
            id=uuid.uuid4(),
            family_id=token_family_id,
            user_id=user.id,
            tenant_id=user.tenant_id,
        )
        db.add(session_record)

    refresh_token = create_refresh_token(
        sub=str(user.id),
        user_id=str(user.id),
        tenant_id=user.tenant_id,
        session_id=str(session_record.id),
    )
    access_token = create_access_token(
        sub=str(user.id),
        email=user.email,
        role=user.role.value,
        tenant_id=user.tenant_id,
        full_name=user.full_name,
        initials=user.initials,
        user_id=str(user.id),
        session_id=str(session_record.id),
    )

    session_record.family_id = token_family_id
    session_record.refresh_token_hash = _token_hash(refresh_token)
    session_record.client_ip = _client_ip(request) or session_record.client_ip
    session_record.user_agent = _user_agent(request) or session_record.user_agent
    session_record.expires_at = refresh_expires_at
    session_record.last_used_at = now
    session_record.revoked_at = None
    session_record.revocation_reason = None
    await db.flush()

    return session_record, TokenBundle(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=get_access_token_expires_in_seconds(),
    )


async def create_login_session(
    db: AsyncSession,
    *,
    user: User,
    request: Request | None,
) -> TokenBundle:
    now = _utcnow()
    user.last_login_at = now
    db.add(user)
    _, bundle = await _issue_session_tokens(db, user=user, request=request)
    return bundle


async def _load_refresh_session(
    db: AsyncSession,
    *,
    claims: dict,
) -> PlatformSession:
    session_id = claims.get("sid")
    user_id = claims.get("user_id")
    tenant_id = claims.get("tenant_id")

    if not session_id or not user_id or not tenant_id:
        raise HTTPException(status_code=401, detail="Refresh token is missing session scope.")

    try:
        session_uuid = uuid.UUID(str(session_id))
        user_uuid = uuid.UUID(str(user_id))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Refresh token session scope is invalid.") from exc

    stored_session = await db.scalar(
        select(PlatformSession).where(
            PlatformSession.id == session_uuid,
            PlatformSession.user_id == user_uuid,
            PlatformSession.tenant_id == tenant_id,
        )
    )
    if stored_session is None:
        raise HTTPException(status_code=401, detail="Refresh token is invalid.")

    return stored_session


async def revoke_session_family(
    db: AsyncSession,
    *,
    family_id: uuid.UUID,
    reason: str,
) -> None:
    now = _utcnow()
    await db.execute(
        update(PlatformSession)
        .where(
            PlatformSession.family_id == family_id,
            PlatformSession.revoked_at.is_(None),
        )
        .values(revoked_at=now, revocation_reason=reason)
    )


async def rotate_refresh_session(
    db: AsyncSession,
    *,
    refresh_token: str,
    request: Request | None,
) -> tuple[User, TokenBundle]:
    now = _utcnow()
    claims = decode_refresh_token(refresh_token)
    stored_session = await _load_refresh_session(db, claims=claims)

    if stored_session.expires_at <= now:
        if stored_session.revoked_at is None:
            stored_session.revoked_at = now
            stored_session.revocation_reason = "expired"
            db.add(stored_session)
            await db.commit()
        raise HTTPException(status_code=401, detail="Refresh token has expired. Please log in again.")

    if stored_session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Session has been revoked. Please log in again.")

    presented_hash = _token_hash(refresh_token)
    if not secrets.compare_digest(stored_session.refresh_token_hash, presented_hash):
        if not (_is_same_client(stored_session, request) and _within_reuse_grace_window(stored_session.last_used_at, now)):
            await revoke_session_family(
                db,
                family_id=stored_session.family_id,
                reason="refresh_token_reuse_detected",
            )
            await db.commit()
            raise HTTPException(status_code=401, detail="Refresh token reuse detected. Please log in again.")

    user = await db.scalar(
        select(User).where(
            User.id == stored_session.user_id,
            User.tenant_id == stored_session.tenant_id,
            User.is_active.is_(True),
        )
    )
    if user is None:
        stored_session.revoked_at = now
        stored_session.revocation_reason = "user_not_active"
        db.add(stored_session)
        await db.commit()
        raise HTTPException(status_code=401, detail="User account not found or deactivated.")

    _, bundle = await _issue_session_tokens(
        db,
        user=user,
        request=request,
        session_record=stored_session,
        family_id=stored_session.family_id,
    )
    user.last_login_at = now

    db.add_all([stored_session, user])
    await db.commit()
    return user, bundle


async def load_active_session_from_claims(
    db: AsyncSession,
    claims: dict,
) -> PlatformSession:
    session_id = claims.get("sid")
    user_id = claims.get("user_id") or claims.get("sub")
    tenant_id = claims.get("tenant_id")

    if not session_id or not user_id or not tenant_id:
        raise HTTPException(status_code=401, detail="Token session is missing required claims.")

    try:
        session_uuid = uuid.UUID(str(session_id))
        user_uuid = uuid.UUID(str(user_id))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Token session scope is invalid.") from exc

    stored_session = await db.scalar(
        select(PlatformSession).where(
            PlatformSession.id == session_uuid,
            PlatformSession.user_id == user_uuid,
            PlatformSession.tenant_id == tenant_id,
        )
    )
    now = _utcnow()
    if stored_session is None:
        raise HTTPException(status_code=401, detail="Session not found.")
    if stored_session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Session has been revoked.")
    if stored_session.expires_at <= now:
        raise HTTPException(status_code=401, detail="Session has expired.")

    return stored_session


async def revoke_refresh_session(
    db: AsyncSession,
    *,
    refresh_token: str,
    reason: str,
) -> bool:
    try:
        claims = decode_refresh_token(refresh_token)
    except HTTPException:
        return False

    try:
        stored_session = await _load_refresh_session(db, claims=claims)
    except HTTPException:
        return False

    if stored_session.revoked_at is None:
        now = _utcnow()
        stored_session.revoked_at = now
        stored_session.revocation_reason = reason
        stored_session.last_used_at = now
        db.add(stored_session)
        await db.commit()

    return True


async def revoke_access_session(
    db: AsyncSession,
    *,
    claims: dict,
    reason: str,
) -> bool:
    try:
        stored_session = await load_active_session_from_claims(db, claims)
    except HTTPException:
        return False

    now = _utcnow()
    stored_session.revoked_at = now
    stored_session.revocation_reason = reason
    stored_session.last_used_at = now
    db.add(stored_session)
    await db.commit()
    return True
