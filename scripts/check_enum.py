import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from arkashri.config import get_settings

async def check():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE typname = 'engagement_type';"))
        rows = result.all()
        print("Enum values for engagement_type:")
        for row in rows:
            print(f"- {row[0]}")

if __name__ == "__main__":
    asyncio.run(check())
