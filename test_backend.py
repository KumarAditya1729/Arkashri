import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
from arkashri.models import EngagementPhase, PhaseStatus, Base
import uuid
import datetime

async def main():
    engine = create_async_engine("postgresql+asyncpg://neondb_owner:npg_X6oZkw3MIVzO@ep-lively-feather-a18z985z-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require")
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        # Use the uuid from the curl command Let's see if we can insert directly into Postgres!
        engagement_id_str = "1e227aa1-3eae-4dbe-806c-9fe1c6a19b75"
        eg_id = uuid.UUID(engagement_id_str)
        entry = EngagementPhase(
            engagement_id=eg_id, # Or literally string
            name="Test Phase 2",
            status=PhaseStatus.UPCOMING,
        )
        session.add(entry)
        try:
            await session.commit()
            print("Successfully inserted phase!")
        except Exception as e:
            print("ERROR!!", str(e))

asyncio.run(main())
