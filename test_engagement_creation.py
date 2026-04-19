import asyncio
import uuid
import sys
import logging

logging.basicConfig(level=logging.DEBUG)

def test_engagement_creation():
    from arkashri.config import get_settings
    settings = get_settings()
    print("Database URL:", settings.database_url)

    from arkashri.db import AsyncSessionLocal
    from arkashri.schemas import EngagementCreate, EngagementType
    from arkashri.services.engagement import create_engagement
    
    async def run():
        async with AsyncSessionLocal() as session:
            try:
                payload = EngagementCreate(
                    tenant_id="default_tenant",
                    client_name="Arkashri Private Limited",
                    engagement_type=EngagementType.FINANCIAL_AUDIT,
                    jurisdiction="IN",
                )
                print("Calling create_engagement...")
                result = await create_engagement(session, payload)
                print("Success! Created Engagement ID:", result.id)
            except Exception as e:
                import traceback
                print("\n=== CRASH TRACEBACK ===")
                traceback.print_exc()
                
    asyncio.run(run())

if __name__ == "__main__":
    test_engagement_creation()
