from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import ApiClient, ClientRole
from arkashri.services.canonical import sha256_hex

KEY_PREFIX = "ark"


@dataclass
class AuthContext:
    client_id: int | None
    client_name: str
    role: ClientRole
    tenant_id: str
    is_system: bool = False


def hash_api_key(raw_key: str) -> str:
    return sha256_hex(raw_key)


def build_system_context(tenant_id: str = "_system") -> AuthContext:
    return AuthContext(client_id=None, client_name="system-dev", role=ClientRole.ADMIN, tenant_id=tenant_id, is_system=True)


async def create_api_client_key(session: AsyncSession, *, name: str, role: ClientRole) -> tuple[ApiClient, str]:
    raw_secret = secrets.token_urlsafe(36)
    raw_key = f"{KEY_PREFIX}_{raw_secret}"
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:12]

    client = ApiClient(
        name=name,
        role=role,
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
    )
    session.add(client)
    await session.flush()
    return client, raw_key


async def resolve_api_client(session: AsyncSession, raw_key: str) -> ApiClient | None:
    key_hash = hash_api_key(raw_key)
    return await session.scalar(select(ApiClient).where(ApiClient.key_hash == key_hash, ApiClient.is_active.is_(True)))


async def touch_client_usage(session: AsyncSession, client: ApiClient) -> None:
    client.last_used_at = datetime.now(timezone.utc)
    session.add(client)
