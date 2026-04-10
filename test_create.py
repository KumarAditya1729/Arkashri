import asyncio
import os

# Use SQLite for testing
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_arkashri.db"

from arkashri.db import engine, Base, AsyncSessionLocal
from arkashri.schemas import EngagementCreate
from arkashri.services.engagement import create_engagement

async def test():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSessionLocal() as session:
        try:
            payload = EngagementCreate(
                tenant_id="default_tenant",
                jurisdiction="IN",
                client_name="Mehta Textiles Ltd",
                engagement_type="FINANCIAL_AUDIT"
            )
            eng = await create_engagement(session, payload)
            print(f"SUCCESS: {eng.id}")
        except Exception as e:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
