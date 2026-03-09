import asyncio
from sqlalchemy import text
from arkashri.db import engine, AsyncSessionLocal

async def clear_demo_data():
    """
    Truncates tables containing demo data to ensure a clean state.
    """
    tables = [
        "materiality_assessment",
        "audit_opinion",
        "seal_session",
        "audit_run_step",
        "audit_run",
        "engagement",
        "audit_event",
        "decision",
        "financial_transaction",
        "exception_case",
    ]
    
    async with AsyncSessionLocal() as session:
        print("🗑️  Clearing demo data from database...")
        for table in tables:
            try:
                # Using TRUNCATE with CASCADE to handle foreign keys
                await session.execute(text(f"TRUNCATE TABLE {table} CASCADE;"))
                print(f"  ✅  Cleared {table}")
            except Exception as e:
                print(f"  ❌  Failed to clear {table}: {e}")
        
        await session.commit()
    print("\n✨  Database is now clean.")

if __name__ == "__main__":
    asyncio.run(clear_demo_data())
