import os
import asyncio
from httpx import AsyncClient, ASGITransport
from arkashri.main import app

async def test_workflow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a mock api client in the DB to pass the auth header check
        # For this test, we might bypass auth by relying on the app's default behavior, or bootstrap it.
        # But wait, setting AUTH_ENFORCED=false in .env works best for testing without bootstrap.
        os.environ["AUTH_ENFORCED"] = "false"
        
        # 1. Create Engagement
        eng_payload = {
            "tenant_id": "test_auditor",
            "jurisdiction": "US",
            "client_name": "Acme Corp",
            "engagement_type": "STATUTORY_AUDIT"
        }
        res = await client.post("/api/v1/engagements/engagements", json=eng_payload)
        assert res.status_code == 201, f"Failed to create engagement: {res.text}"
        engagement_id = res.json()["id"]
        print(f"Engagement Created: {engagement_id}")
        
        # 2. Compute Materiality
        mat_payload = {
            "basis": "REVENUE",
            "basis_amount": 10000000.0,
            "overall_percentage": 1.0,
            "performance_percentage": 75.0,
            "trivial_threshold_percentage": 5.0,
            "notes": "Standard metrics applied."
        }
        res = await client.post(f"/api/v1/engagements/engagements/{engagement_id}/materiality", json=mat_payload)
        assert res.status_code == 201, f"Failed to compute materiality: {res.text}"
        print(f"Materiality Computed: Overall={res.json()['overall_materiality']}")
        
        # 3. Generate Opinion
        op_payload = {}
        res = await client.post(f"/api/v1/engagements/engagements/{engagement_id}/opinion", json=op_payload)
        assert res.status_code == 201, f"Failed to generate opinion: {res.text}"
        print(f"Draft Opinion Generated: Type={res.json()['opinion_type']}")

if __name__ == "__main__":
    asyncio.run(test_workflow())
