import asyncio
from httpx import AsyncClient, ASGITransport
import sys

from arkashri.config import get_settings
s = get_settings()
s.redis_url = None

from arkashri.main import app

async def test():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/engagements/engagements",
            json={
                "client_name": "Testing Valid Router",
                "engagement_type": "FINANCIAL_AUDIT",
                "jurisdiction": "IN",
                "tenant_id": "some_tenant"
            },
            headers={"Authorization": "Bearer arkashri-bootstrap"}
        )
        print(response.status_code)
        print(response.json())

if __name__ == "__main__":
    asyncio.run(test())
