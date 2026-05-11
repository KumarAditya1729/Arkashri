# pyre-ignore-all-errors
import asyncio
import datetime
import structlog
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis_async

from arkashri.config import get_settings
from arkashri.services.blockchain_adapter import ADAPTERS

logger = structlog.get_logger("services.health")

async def check_database(db: AsyncSession) -> bool:
    try:
        await db.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))
        return False

async def check_redis() -> bool:
    settings = get_settings()
    redis_url = (settings.redis_url or "").strip()
    parsed = urlparse(redis_url)
    if not redis_url or parsed.scheme not in {"redis", "rediss"}:
        logger.warning("health_check_redis_not_configured")
        return False
    try:
        r = redis_async.from_url(redis_url)
        try:
            await r.ping()
            return True
        finally:
            await r.close()
    except Exception as e:
        logger.error("health_check_redis_failed", error=str(e))
        return False

async def check_openai() -> bool:
    """Checks if the configured OpenAI-compatible provider can serve the selected model."""
    settings = get_settings()
    if not settings.openai_api_key:
        return False
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        # Groq and other OpenAI-compatible providers may not support models.list()
        # consistently, so use the same chat path the app relies on with 1 token.
        await client.chat.completions.create(
            model=settings.ai_model_primary,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
        )
        return True
    except Exception as e:
        logger.error("health_check_openai_failed", error=str(e))
        return False

def _openai_status_from_config() -> str:
    settings = get_settings()
    return "unconfigured" if not settings.openai_api_key else "unreachable"

def _configured_blockchain_adapters() -> set[str]:
    settings = get_settings()
    configured: set[str] = set()
    if settings.polkadot_enabled:
        configured.add("POLKADOT")
    if settings.hash_notary_url:
        configured.add("HASH_NOTARY")
    return configured

async def check_blockchain() -> dict[str, bool]:
    results = {}
    configured = _configured_blockchain_adapters()
    for key, adapter in ADAPTERS.items():
        if key not in configured:
            continue
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
    
    openai_status = "ok" if openai_ok else _openai_status_from_config()

    if not (db_ok and redis_ok):
        status = "unhealthy"
    elif openai_status == "unreachable" or not all(blockchain_results.values()):
        status = "degraded"
    else:
        status = "healthy"
        
    return {
        "status": status,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dependencies": {
            "database": "ok" if db_ok else "unreachable",
            "redis": "ok" if redis_ok else "unreachable",
            "openai": openai_status,
            "blockchain": blockchain_results,
        }
    }
