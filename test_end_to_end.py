import asyncio, httpx, uuid, json
from sqlalchemy import select
from arkashri.db import AsyncSessionLocal
from arkashri.models import Tenant, User, ProfessionalJudgment, AuditOpinion

BASE = "http://localhost:8000/api/v1"

async def setup_db():
    async with AsyncSessionLocal() as session:
        t = await session.execute(select(Tenant).limit(1))
        tenant = t.scalar_one_or_none()
        if not tenant:
            tenant = Tenant(id=uuid.uuid4(), name="Test Tenant", api_key="ark_live_test123", jurisdiction="in")
            session.add(tenant)
            await session.commit()
            
        u = await session.execute(select(User).limit(1))
        user = u.scalar_one_or_none()
        if not user:
            user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="test@ark.com", full_name="CA Test", role="ADMIN", icai_reg_no="123456")
            session.add(user)
            await session.commit()
            
        return tenant.api_key, user

async def run():
    api_key, user = await setup_db()
    c = httpx.AsyncClient(timeout=30, headers={"X-API-Key": api_key})
    
    print("API KEY USED:", api_key)
    print("\n=== STEP 7-11: END TO END API VALIDATION ===")
    
    print("\n1. ENGAGEMENT")
    r = await c.post(f"{BASE}/engagements/engagements", json={
        "client_name": "E2E Test Corp", "engagement_type": "FINANCIAL_AUDIT",
        "reporting_period_start": "2024-04-01", "reporting_period_end": "2025-03-31",
        "jurisdiction": "IN", "workflow_template_id": "financial_audit_v1"
    })
    print(r.status_code, r.text[:200])
    eng_id = r.json()["id"] if r.status_code == 201 else None
    
    print("\n2. ERP DATA")
    r = await c.post(f"{BASE}/erp/ingest", json={
        "engagement_id": eng_id, "erp_system": "quickbooks",
        "records": [
            {"Id": "1", "TxnDate": "2024-05-01", "Amount": 100000, "detail": {"PostingType": "Debit"}, "AccountRef": {"value": "Cash"}}
        ]
    })
    print(r.status_code, r.text[:200])

    print("\n3. RISK ENGINE")
    r = await c.post(f"{BASE}/engagements/engagements/{eng_id}/risk/compute")
    print(r.status_code, r.text[:200])

    print("\n4. ORCHESTRATION")
    r = await c.post(f"{BASE}/orchestration/runs", json={"engagement_id": eng_id, "workflow_template_id": "financial_audit_v1"})
    print(r.status_code, r.text[:200])
    if r.status_code == 200:
        run_id = r.json()["id"]
        r = await c.post(f"{BASE}/orchestration/runs/{run_id}/execute")
        print("Execute:", r.status_code, r.text[:200])

    print("\n5. GOING CONCERN (Triggers Judgment Gate)")
    r = await c.post(f"{BASE}/v1/going-concern/{eng_id}/assess", json={
        "total_assets": 10000, "total_liabilities": 14000, "current_assets": 1200, "current_liabilities": 4500,
        "revenue": 5000, "ebit": -800, "net_income": -1100, "operating_cash_flow": -950,
        "industry_sector": "Manufacturing", "auto_flag_judgment": True
    })
    print(r.status_code, r.text[:300])

    print("\n6. JUDGMENT GATE")
    async with AsyncSessionLocal() as session:
        t = await session.execute(select(ProfessionalJudgment).filter_by(engagement_id=uuid.UUID(eng_id), status="PENDING"))
        judgments = t.scalars().all()
        print(f"Found {len(judgments)} pending judgments.")
        for j in judgments:
            r = await c.post(f"{BASE}/judgments/{j.id}/sign-off", json={"notes": "Reviewed", "user_id": str(user.id)})
            print("Sign off:", r.status_code, r.text[:200])

    print("\n7. OPINION")
    r = await c.post(f"{BASE}/engagements/engagements/{eng_id}/opinion", json={"jurisdiction": "IN", "reporting_framework": "IND_AS"})
    print(r.status_code, r.text[:300])

    print("\n8. SEAL")
    r = await c.post(f"{BASE}/engagements/engagements/{eng_id}/seal")
    print(r.status_code, r.text[:300])

asyncio.run(run())
