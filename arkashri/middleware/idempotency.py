# pyre-ignore-all-errors
import json
import time
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import structlog

logger = structlog.get_logger("middleware.idempotency")

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Enterprise-Grade Idempotency and Replay Protection.
    Features:
      - X-Idempotency-Key: Cache/Retrieve response snapshots.
      - X-Timestamp: Validates request age (rejects > 300s drift).
      - X-Nonce: Tracks unique request identifiers in Redis to prevent replays.
    """
    def __init__(
        self, 
        app, 
        redis_client_getter: Optional[Callable] = None,
        expiry: int = 86400,  # 24 hours for response cache
        nonce_expiry: int = 3600 # 1 hour for nonce tracking
    ):
        super().__init__(app)
        self.redis_client_getter = redis_client_getter
        self.expiry = expiry
        self.nonce_expiry = nonce_expiry

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in ("POST", "PATCH", "PUT"):
            return await call_next(request)

        idempotency_key = request.headers.get("X-Idempotency-Key")
        timestamp = request.headers.get("X-Timestamp")
        nonce = request.headers.get("X-Nonce")

        if not idempotency_key:
            return await call_next(request)

        redis = self.redis_client_getter() if self.redis_client_getter else None
        if not redis:
            return await call_next(request)

        tenant_id = request.headers.get("X-Arkashri-Tenant", "default")
        
        # ── 1. Replay Protection: Timestamp Drift Check ──────────────────────
        if timestamp:
            try:
                request_time = int(timestamp)
                now = int(time.time())
                if abs(now - request_time) > 300: # 5 minutes
                    logger.warning("idempotency_replay_rejected_timestamp", 
                                   key=idempotency_key, drift=now - request_time)
                    return JSONResponse(
                        status_code=400,
                        content={"error": "Timestamp drift exceeds 300 seconds. Check system clock."}
                    )
            except ValueError:
                return JSONResponse(status_code=400, content={"error": "Invalid X-Timestamp header"})

        # ── 2. Replay Protection: Nonce Collision Check ───────────────────────
        if nonce:
            nonce_key = f"nonce:{tenant_id}:{idempotency_key}:{nonce}"
            # SETNX (Set if Not Exists)
            if not await redis.set(nonce_key, "1", ex=self.nonce_expiry, nx=True):
                logger.warning("idempotency_replay_rejected_nonce", 
                               key=idempotency_key, nonce=nonce, tenant=tenant_id)
                return JSONResponse(
                    status_code=409,
                    content={"error": "Duplicate request detected (Nonce collision)."}
                )

        cache_key = f"idempotency:{tenant_id}:{idempotency_key}"

        # ── 3. Response Cache Check ──────────────────────────────────────────
        cached = await redis.get(cache_key)
        if cached:
            logger.info("idempotency_cache_hit", key=idempotency_key, tenant=tenant_id)
            data = json.loads(cached)
            return JSONResponse(
                content=data["body"],
                status_code=data["status_code"],
                headers={**data["headers"], "X-Idempotency-Hit": "true"}
            )

        # ── 4. Process Request ───────────────────────────────────────────────
        response = await call_next(request)

        # ── 5. Cache Successful Responses ────────────────────────────────────
        if 200 <= response.status_code < 300:
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
            
            return JSONResponse(
                content=body_json,
                status_code=response.status_code,
                headers=dict(response.headers)
            )

        return response
