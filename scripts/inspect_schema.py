import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from arkashri.config import get_settings

async def inspect():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        print("--- Table with Schemas ---")
        result = await conn.execute(text(
            "SELECT table_schema, table_name FROM information_schema.tables WHERE table_name = 'audit_playbook';"
        ))
        for row in result:
            print(f"Table: {row[0]}.{row[1]}")
            
        print("\n--- Enum with Schemas ---")
        result = await conn.execute(text(
            "SELECT nspname, typname FROM pg_type JOIN pg_namespace ON pg_type.typnamespace = pg_namespace.oid WHERE typname = 'engagement_type';"
        ))
        for row in result:
            print(f"Enum: {row[0]}.{row[1]}")
            
        print("\n--- Enum Values detailing schemas ---")
        result = await conn.execute(text(
            """
            SELECT nspname, enumlabel 
            FROM pg_enum 
            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid 
            JOIN pg_namespace ON pg_type.typnamespace = pg_namespace.oid 
            WHERE typname = 'engagement_type';
            """
        ))
        for row in result:
            print(f"Schema: {row[0]}, Value: {row[1]}")

if __name__ == "__main__":
    asyncio.run(inspect())
