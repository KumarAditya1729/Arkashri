import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from arkashri.config import get_settings

async def inspect():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        print("--- Table: audit_playbook ---")
        result = await conn.execute(text(
            "SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_name = 'audit_playbook';"
        ))
        for row in result:
            print(f"Col: {row[0]}, Type: {row[1]}, UDT: {row[2]}")
            
        print("\n--- Enum: engagement_type ---")
        result = await conn.execute(text(
            "SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE typname = 'engagement_type';"
        ))
        for row in result:
            print(f"- {row[0]}")

if __name__ == "__main__":
    asyncio.run(inspect())
