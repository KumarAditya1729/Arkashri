import asyncio
import uuid
import datetime
from sqlalchemy import text
from arkashri.db import engine

async def fix():
    user_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
    session_id = uuid.UUID("660e8400-e29b-41d4-a716-446655440000")
    tenant_id = "test-tenant"
    email = "test@example.com"
    
    async with engine.begin() as conn:
        # 1. Update user ID
        await conn.execute(
            text("UPDATE platform_user SET id=:id WHERE email=:email"),
            {"id": user_id, "email": email}
        )
        
        # 2. Insert session
        # First delete existing to be idempotent
        await conn.execute(
            text("DELETE FROM platform_session WHERE id=:id"),
            {"id": session_id}
        )
        
        now = datetime.datetime.now(datetime.timezone.utc)
        expires_at = now + datetime.timedelta(days=7)
        
        await conn.execute(
            text("""
                INSERT INTO platform_session (id, user_id, tenant_id, family_id, refresh_token_hash, expires_at, created_at, last_used_at)
                VALUES (:id, :user_id, :tenant_id, :family_id, :hash, :expires_at, :now, :now)
            """),
            {
                "id": session_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "family_id": uuid.uuid4(),
                "hash": "dummy",
                "expires_at": expires_at,
                "now": now
            }
        )
    print(f"✅ User {user_id} and Session {session_id} prepared.")

if __name__ == "__main__":
    asyncio.run(fix())
