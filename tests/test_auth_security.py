# pyre-ignore-all-errors
from datetime import datetime, timedelta, timezone
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from arkashri.dependencies import load_active_user_from_claims
from arkashri.models import PlatformSession, User, UserRole
from arkashri.services.jwt_service import create_access_token, create_ws_ticket, decode_ws_ticket


def _build_user(*, tenant_id: str = "default_tenant") -> User:
    return User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="auditor@example.com",
        hashed_password="hashed-password",
        full_name="Asha Rao",
        initials="AR",
        role=UserRole.ADMIN,
        is_active=True,
    )


def _build_session(user: User) -> PlatformSession:
    return PlatformSession(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        user_id=user.id,
        tenant_id=user.tenant_id,
        refresh_token_hash="hashed-refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        last_used_at=datetime.now(timezone.utc),
        revoked_at=None,
    )


@pytest.mark.asyncio
async def test_load_active_user_from_claims_returns_active_user() -> None:
    user = _build_user()
    session_record = _build_session(user)
    session = AsyncMock()
    session.scalar.side_effect = [session_record, user]

    claims = {
        "user_id": str(user.id),
        "tenant_id": user.tenant_id,
        "sid": str(session_record.id),
    }

    resolved = await load_active_user_from_claims(session, claims)

    assert resolved.id == user.id


@pytest.mark.asyncio
async def test_load_active_user_from_claims_rejects_missing_user() -> None:
    user = _build_user()
    session_record = _build_session(user)
    session = AsyncMock()
    session.scalar.side_effect = [session_record, None]

    with pytest.raises(HTTPException) as excinfo:
        await load_active_user_from_claims(
            session,
            {
                "user_id": str(user.id),
                "tenant_id": user.tenant_id,
                "sid": str(session_record.id),
            },
        )

    assert excinfo.value.status_code == 401


def test_ws_ticket_round_trip() -> None:
    ticket = create_ws_ticket(
        user_id=str(uuid.uuid4()),
        tenant_id="default_tenant",
        jurisdiction="IN",
    )

    claims = decode_ws_ticket(ticket)

    assert claims["type"] == "ws"
    assert claims["tenant_id"] == "default_tenant"
    assert claims["jurisdiction"] == "IN"


def test_ws_ticket_rejects_access_token() -> None:
    access_token = create_access_token(
        sub=str(uuid.uuid4()),
        email="auditor@example.com",
        role="ADMIN",
        tenant_id="default_tenant",
        full_name="Asha Rao",
        initials="AR",
        user_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
    )

    with pytest.raises(HTTPException) as excinfo:
        decode_ws_ticket(access_token)

    assert excinfo.value.status_code == 401
