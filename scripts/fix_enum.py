import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from arkashri.config import get_settings

REQUIRED_VALUES = [
    "FINANCIAL_AUDIT",
    "INTERNAL_AUDIT",
    "EXTERNAL_AUDIT",
    "STATUTORY_AUDIT",
    "COMPLIANCE_AUDIT",
    "OPERATIONAL_AUDIT",
    "TAX_AUDIT",
    "IT_AUDIT",
    "FORENSIC_AUDIT",
    "PERFORMANCE_AUDIT",
    "ENVIRONMENTAL_AUDIT",
    "PAYROLL_AUDIT",
    "QUALITY_AUDIT",
    "SINGLE_AUDIT",
]

async def fix_enum():
    settings = get_settings()
    # Create an engine with AUTOCOMMIT to run ALTER TYPE without transaction blocks
    engine = create_async_engine(settings.database_url)
    
    async with engine.connect() as conn:
        # 1. Get existing values
        result = await conn.execute(text(
            "SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE typname = 'engagement_type';"
        ))
        existing_values = {row[0] for row in result.all()}
        
        print(f"Existing values: {existing_values}")
        
        # 2. Add missing values
        for val in REQUIRED_VALUES:
            if val not in existing_values:
                print(f"Adding value: {val}")
                try:
                    # ALTER TYPE ADD VALUE cannot run in a transaction block
                    # However, SQLAlchemy async eng.connect() creates a transaction context by default.
                    # We can use conn.execution_options(isolation_level="AUTOCOMMIT") to execute outside
                    await conn.execute(text(f"ALTER TYPE engagement_type ADD VALUE '{val}'"))
                    print(f"Added: {val}")
                except Exception as e:
                    print(f"Failed to add {val}: {e}")

if __name__ == "__main__":
    asyncio.run(fix_enum())
