#!/usr/bin/env python3
"""
scripts/seed_admin.py — Bootstrap first ADMIN user
===================================================
Solves the chicken-and-egg problem: POST /auth/users requires ADMIN role,
but there's no ADMIN user yet on a fresh install.

Usage:
    python scripts/seed_admin.py

Or via env vars:
    SEED_EMAIL=admin@yourfirm.com SEED_PASSWORD=SecurePass@1 python scripts/seed_admin.py

Idempotent: safe to run multiple times. Skips if admin already exists.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from arkashri.config import get_settings
from arkashri.models import User, UserRole
from arkashri.services.password import hash_password


async def seed() -> None:
    settings = get_settings()

    email     = os.getenv("SEED_EMAIL",    "admin@arkashri.io")
    password  = os.getenv("SEED_PASSWORD", "Admin@2026!")
    full_name = os.getenv("SEED_NAME",     "Operator Principal")
    tenant_id = os.getenv("SEED_TENANT",   "default_tenant")
    initials  = os.getenv("SEED_INITIALS", "OP")

    engine  = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        existing = (await session.scalars(
            select(User).where(User.email == email, User.tenant_id == tenant_id)
        )).first()

        if existing:
            print(f"✅ Admin user already exists: {existing.email} (role={existing.role.value})")
            return

        admin = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            initials=initials.upper(),
            role=UserRole.ADMIN,
            is_active=True,
            created_by="seed_admin.py",
        )
        session.add(admin)
        await session.commit()

    await engine.dispose()

    print(f"""
╔══════════════════════════════════════════════════════╗
║         Admin User Created Successfully              ║
╠══════════════════════════════════════════════════════╣
║  Email:     {email:<40} ║
║  Password:  {password:<40} ║
║  Role:      ADMIN                                    ║
║  Tenant:    {tenant_id:<40} ║
╠══════════════════════════════════════════════════════╣
║  POST /api/v1/token/  to get your JWT                ║
╚══════════════════════════════════════════════════════╝

⚠️  Change this password immediately after first login!
""")


if __name__ == "__main__":
    asyncio.run(seed())
