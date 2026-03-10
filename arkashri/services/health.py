import asyncio
import datetime
import structlog
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis_async

from arkashri.config import get_settings
from arkashri.services.blockchain_adapter import ADAPTERS

logger = structlog.get_logger("services.health")
settings = get_settings()

async def check_database(db: AsyncSession) -> bool:
    try:
        await db.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))
        return False

async def check_redis() -> bool:
    try:
        r = redis_async.from_url(settings.redis_url)
        await r.ping()
        return True
    except Exception as e:
        logger.error("health_check_redis_failed", error=str(e))
        return False

async def check_openai() -> bool:
    """Checks if OpenAI is reachable and the API key is valid (via a cheap models list call)."""
    if not settings.openai_api_key:
        return False
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        # We don't want to burn tokens, so just list models which is free/low-cost & verifies key/connectivity
        await client.models.list()
        return True
    except Exception as e:
        logger.error("health_check_openai_failed", error=str(e))
        return False

async def check_blockchain() -> dict[str, bool]:
    results = {}
    for key, adapter in ADAPTERS.items():
        results[key] = await adapter.check_health()
    return results

async def get_full_health_status(db: AsyncSession) -> dict[str, Any]:
    """Gather all dependency health statuses."""
    # Run DB check first to avoid session sharing issues in gather
    db_ok = await check_database(db)
    
    redis_task = check_redis()
    openai_task = check_openai()
    blockchain_task = check_blockchain()
    
    redis_ok, openai_ok, blockchain_results = await asyncio.gather(
        redis_task, openai_task, blockchain_task
    )
    
    if not (db_ok and redis_ok):
        status = "unhealthy"
    elif not (openai_ok and all(blockchain_results.values())):
        status = "degraded"
    else:
        status = "healthy"
        
    return {
        "status": status,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dependencies": {
            "database": "ok" if db_ok else "unreachable",
            "redis": "ok" if redis_ok else "unreachable",
            "openai": "ok" if openai_ok else "unreachable",
            "blockchain": blockchain_results,
        }
    }
