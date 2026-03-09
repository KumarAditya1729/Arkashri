import hashlib
import json
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import structlog

logger = structlog.get_logger("middleware.idempotency")

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to ensure idempotency for POST/PATCH/PUT requests.
    Uses the 'X-Idempotency-Key' header to store and retrieve response snapshots from Redis.
    """
    def __init__(
        self, 
        app, 
        redis_client_getter: Optional[Callable] = None,
        expiry: int = 86400  # 24 hours
    ):
        super().__init__(app)
        self.redis_client_getter = redis_client_getter
        self.expiry = expiry

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in ("POST", "PATCH", "PUT"):
            return await call_next(request)

        idempotency_key = request.headers.get("X-Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)

        redis = self.redis_client_getter() if self.redis_client_getter else None
        if not redis:
            return await call_next(request)

        tenant_id = request.headers.get("X-Arkashri-Tenant", "default")
        cache_key = f"idempotency:{tenant_id}:{idempotency_key}"

        # 1. Check if we have a cached response
        cached = await redis.get(cache_key)
        if cached:
            logger.info("idempotency_cache_hit", key=idempotency_key, tenant=tenant_id)
            data = json.loads(cached)
            return JSONResponse(
                content=data["body"],
                status_code=data["status_code"],
                headers={**data["headers"], "X-Idempotency-Hit": "true"}
            )

        # 2. Process request
        response = await call_next(request)

        # 3. Only cache successful responses (2xx)
        if 200 <= response.status_code < 300:
            # We need to capture the response body to cache it
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk
            
            try:
                body_json = json.loads(response_body.decode("utf-8"))
                cache_data = {
                    "body": body_json,
                    "status_code": response.status_code,
                    "headers": dict(response.headers)
                }
                await redis.setex(cache_key, self.expiry, json.dumps(cache_data))
                logger.info("idempotency_cache_stored", key=idempotency_key, tenant=tenant_id)
            except Exception as e:
                logger.warning("idempotency_cache_failed", error=str(e))
            
            # Reconstruct the response since we consumed the stream
            return JSONResponse(
                content=body_json,
                status_code=response.status_code,
                headers=dict(response.headers)
            )

        return response
