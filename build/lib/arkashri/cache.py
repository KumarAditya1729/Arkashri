import json
import redis.asyncio as redis
from typing import Any

from arkashri.config import get_settings

# Global Redis Connection Pool
settings = get_settings()
redis_client = redis.from_url(settings.redis_url, decode_responses=True)

async def cache_get(key: str) -> dict[str, Any] | None:
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return None

async def cache_set(key: str, value: dict[str, Any], ttl: int = 3600) -> None:
    await redis_client.setex(key, ttl, json.dumps(value))

async def cache_delete(key: str) -> None:
    await redis_client.delete(key)
