# pyre-ignore-all-errors
"""
scripts/concurrency_stress_test.py
==================================
Real-world concurrency stress test for the Arkashri Audit Event Chain.

This script blasts a target PostgreSQL database with 100 concurrent
`append_audit_event` calls for the same engagement to verify that the
`SELECT FOR UPDATE` fix prevents hash-chain forks under heavy contention.

Usage:
  DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/dbname" \\
  python scripts/concurrency_stress_test.py
"""
import asyncio
import os
import sys
import uuid
import time
import random
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# Add the project root to sys.path so we can import arkashri modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from arkashri.services.audit import append_audit_event, verify_audit_chain
from arkashri.models import Base

async def setup_db():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL environment variable is required.")
        sys.exit(1)
    
    print(f"Connecting to {db_url.split('@')[-1]}...")
    engine = create_async_engine(db_url, echo=False, pool_size=50, max_overflow=50)
    
    # Ensure tables exist (for test DBs)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def fire_concurrent_appends(SessionLocal, tenant_id: str, jurisdiction: str, engagement_id: uuid.UUID, num_tasks: int = 100):
    async def worker(worker_id: int):
        async with SessionLocal() as session:
            try:
                await append_audit_event(
                    session,
                    tenant_id=tenant_id,
                    jurisdiction=jurisdiction,
                    engagement_id=engagement_id,
                    event_type="STRESS_TEST",
                    entity_type="worker",
                    entity_id=str(worker_id),
                    payload={"worker_id": worker_id, "timestamp": time.time()}
                )
                
                # 🛑 CHAOS INJECTION: Network jitter & forced mid-transaction rollbacks
                await asyncio.sleep(random.uniform(0.01, 0.1))
                if random.random() < 0.1:
                    raise Exception("Chaos Rollback - simulating a dying runner mid-flight")
                    
                await session.commit()
                return True
            except Exception as e:
                # Expecting some contention, but NO forks
                # Depending on isolation level, some might get serialized serialization errors
                await session.rollback()
                return False

    print(f"🔥 Firing {num_tasks} concurrent appends...")
    tasks = [worker(i) for i in range(num_tasks)]
    start_time = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successes = sum(1 for r in results if r is True)
    print(f"✅ Completed in {time.time() - start_time:.2f}s. Successful inserts: {successes}/{num_tasks}")

async def main():
    SessionLocal = await setup_db()
    
    tenant_id = "concurrency-tester"
    jurisdiction = "IN"
    engagement_id = uuid.uuid4()
    
    async with SessionLocal() as session:
        # Seed initial event to start the chain
        await append_audit_event(
            session, tenant_id, jurisdiction, engagement_id, "SEED", "test", "0", {"msg": "baseline"}
        )
        await session.commit()
    
    # Run the blast
    await fire_concurrent_appends(SessionLocal, tenant_id, jurisdiction, engagement_id, num_tasks=100)
    
    print("🔍 Verifying audit chain integrity...")
    async with SessionLocal() as session:
        ok, issues, count = await verify_audit_chain(
            session, tenant_id=tenant_id, jurisdiction=jurisdiction, engagement_id=engagement_id
        )
        
        if ok:
            print(f"🎉 SUCCESS: Chain is perfectly linear. Total events: {count}")
            sys.exit(0)
        else:
            print(f"🚨 FAILURE: Chain forks detected! Issues: {issues}")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
