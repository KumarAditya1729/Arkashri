import os
import sys
import asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from openai import AsyncOpenAI

load_dotenv()

async def check_readiness():
    print("🚀 Running Pre-Audit Health Check...")
    
    # 1. Database Check
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL is missing!")
        sys.exit(1)
        
    try:
        print(f"🔌 Connecting to Database at {db_url.split('@')[-1]}...")
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            print("✅ Database connection established and verified!")
    except Exception as e:
        print(f"❌ Database connection failed: {str(e)}")
        sys.exit(1)

    # 2. OpenAI / LLM Check
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("❌ OPENAI_API_KEY is missing!")
        sys.exit(1)
        
    try:
        print("🤖 Checking OpenAI Intelligence Engine...")
        client = AsyncOpenAI(api_key=openai_key)
        # Quick, minimal ping to check token validity
        response = await client.chat.completions.create(
            model=os.getenv("AI_MODEL_PRIMARY", "gpt-4-turbo"),
            messages=[{"role": "user", "content": "Ping"}],
            max_tokens=5
        )
        print("✅ OpenAI Intelligence Engine is online and responding!")
    except Exception as e:
        print(f"❌ OpenAI Engine failed: {str(e)}")
        sys.exit(1)

    print("\n🎉 ALL SYSTEMS GO! Arkashri is fully ready for Production Audits!")

if __name__ == "__main__":
    asyncio.run(check_readiness())
