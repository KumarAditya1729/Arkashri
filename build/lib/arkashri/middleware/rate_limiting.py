# pyre-ignore-all-errors
"""
Advanced rate limiting and throttling middleware for production
Provides multi-level rate limiting with Redis backend and intelligent throttling
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum

import redis.asyncio as redis
from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from arkashri.config import get_settings
from arkashri.logging_config import security_logger

logger = structlog.get_logger(__name__)


class RateLimitScope(str, Enum):
    GLOBAL = "global"
    TENANT = "tenant"
    USER = "user"
    IP = "ip"
    ENDPOINT = "endpoint"


@dataclass
class RateLimitRule:
    """Rate limit rule configuration"""
    requests: int
    window_seconds: int
    scope: RateLimitScope
    burst_size: Optional[int] = None
    penalty_seconds: Optional[int] = None


@dataclass
class RateLimitResult:
    """Rate limit check result"""
    allowed: bool
    remaining: int
    reset_time: int
    retry_after: Optional[int] = None
    rule_id: Optional[str] = None


class RateLimitBackend:
    """Redis-based rate limiting backend"""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None
        self.logger = structlog.get_logger("rate_limit_backend")
    
    async def connect(self):
        """Connect to Redis"""
        if not self._redis:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            self.logger.info("rate_limit_redis_connected")
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self._redis:
            await self._redis.close()
            self._redis = None
    
    async def check_rate_limit(
        self,
        key: str,
        rule: RateLimitRule
    ) -> RateLimitResult:
        """Check rate limit using sliding window algorithm"""
        if not self._redis:
            await self.connect()
        
        now = int(time.time())
        window_start = now - rule.window_seconds
        
        # Use Redis sorted set for sliding window
        pipe = self._redis.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count current requests
        pipe.zcard(key)
        
        # Add current request
        pipe.zadd(key, {str(now): now})
        
        # Set expiration
        pipe.expire(key, rule.window_seconds * 2)
        
        results = await pipe.execute()
        current_requests = results[1]
        
        # Check if rate limit exceeded
        allowed = current_requests < rule.requests
        remaining = max(0, rule.requests - current_requests - 1)
        reset_time = now + rule.window_seconds
        
        retry_after = None
        if not allowed:
            retry_after = rule.window_seconds
            
            # Apply penalty if configured
            if rule.penalty_seconds:
                penalty_key = f"{key}:penalty"
                await self._redis.setex(penalty_key, rule.penalty_seconds, "1")
        
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_time=reset_time,
            retry_after=retry_after,
            rule_id=f"{rule.scope.value}:{rule.requests}:{rule.window_seconds}"
        )
    
    async def is_penalized(self, key: str) -> bool:
        """Check if client is currently penalized"""
        if not self._redis:
            await self.connect()
        
        penalty_key = f"{key}:penalty"
        return await self._redis.exists(penalty_key) > 0


class TokenBucketRateLimiter:
    """Token bucket algorithm for smoother rate limiting"""
    
    def __init__(self, redis_backend: RateLimitBackend):
        self.backend = redis_backend
        self.logger = structlog.get_logger("token_bucket")
    
    async def check_token_bucket(
        self,
        key: str,
        capacity: int,
        refill_rate: float,
        tokens_requested: int = 1
    ) -> RateLimitResult:
        """Check token bucket rate limit"""
        if not self.backend._redis:
            await self.backend.connect()
        
        now = time.time()
        
        # Get current bucket state
        bucket_key = f"bucket:{key}"
        pipe = self.backend._redis.pipeline()
        
        pipe.hgetall(bucket_key)
        pipe.ttl(bucket_key)
        
        results = await pipe.execute()
        bucket_data = results[0] or {}
        ttl = results[1]
        
        # Parse bucket state
        tokens = float(bucket_data.get("tokens", capacity))
        last_refill = float(bucket_data.get("last_refill", now))
        
        # Refill tokens based on time elapsed
        time_passed = now - last_refill
        tokens = min(capacity, tokens + time_passed * refill_rate)
        
        # Check if enough tokens
        allowed = tokens >= tokens_requested
        remaining = int(tokens) if allowed else 0
        
        if allowed:
            tokens -= tokens_requested
        
        # Update bucket state
        pipe.hset(bucket_key, {
            "tokens": tokens,
            "last_refill": now
        })
        
        # Set expiration if not set
        if ttl == -1:
            pipe.expire(bucket_key, 3600)  # 1 hour default
        
        await pipe.execute()
        
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_time=int(now + (capacity - tokens) / refill_rate) if not allowed else int(now + 60),
        )


class AdaptiveRateLimiter:
    """Adaptive rate limiting based on system load and response times"""
    
    def __init__(self, redis_backend: RateLimitBackend):
        self.backend = redis_backend
        self.logger = structlog.get_logger("adaptive_rate_limiter")
        self._load_factor: Dict[str, float] = {}
    
    async def adjust_limits(self, endpoint: str, response_time: float):
        """Adjust rate limits based on response times"""
        # Simple adaptive logic: reduce limits if response times are high
        current_load = self._load_factor.get(endpoint, 1.0)
        
        if response_time > 1.0:  # High response time
            new_load = max(0.5, current_load * 0.9)  # Reduce by 10%
        elif response_time < 0.1:  # Low response time
            new_load = min(2.0, current_load * 1.05)  # Increase by 5%
        else:
            new_load = current_load
        
        self._load_factor[endpoint] = new_load
        
        self.logger.info(
            "adaptive_rate_limit_adjustment",
            endpoint=endpoint,
            response_time=response_time,
            load_factor=new_load
        )
    
    def get_adjusted_requests(self, base_requests: int, endpoint: str) -> int:
        """Get adjusted request limit based on load factor"""
        load_factor = self._load_factor.get(endpoint, 1.0)
        return max(1, int(base_requests * load_factor))


class ProductionRateLimitMiddleware(BaseHTTPMiddleware):
    """Production-ready rate limiting middleware"""
    
    def __init__(self, app, redis_url: str):
        super().__init__(app)
        self.backend = RateLimitBackend(redis_url)
        self.token_bucket = TokenBucketRateLimiter(self.backend)
        self.adaptive_limiter = AdaptiveRateLimiter(self.backend)
        self.settings = get_settings()
        self.logger = structlog.get_logger("rate_limit_middleware")
        
        # Define rate limit rules
        self.rules = self._define_rules()
    
    def _define_rules(self) -> List[Tuple[str, RateLimitRule]]:
        """Define rate limiting rules for different scenarios"""
        rules = [
            # Global limits
            ("global", RateLimitRule(
                requests=1000,
                window_seconds=60,
                scope=RateLimitScope.GLOBAL
            )),
            
            # Per-tenant limits
            ("tenant", RateLimitRule(
                requests=500,
                window_seconds=60,
                scope=RateLimitScope.TENANT
            )),
            
            # Per-user limits
            ("user", RateLimitRule(
                requests=100,
                window_seconds=60,
                scope=RateLimitScope.USER
            )),
            
            # Per-IP limits
            ("ip", RateLimitRule(
                requests=200,
                window_seconds=60,
                scope=RateLimitScope.IP,
                penalty_seconds=300  # 5 minute penalty for abuse
            )),
            
            # Endpoint-specific limits
            ("auth", RateLimitRule(
                requests=10,
                window_seconds=60,
                scope=RateLimitScope.ENDPOINT,
                penalty_seconds=900  # 15 minute penalty for auth abuse
            )),
            
            ("file_upload", RateLimitRule(
                requests=20,
                window_seconds=60,
                scope=RateLimitScope.ENDPOINT
            )),
            
            ("api_heavy", RateLimitRule(
                requests=50,
                window_seconds=60,
                scope=RateLimitScope.ENDPOINT
            )),
        ]
        
        return rules
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with rate limiting"""
        start_time = time.time()
        
        # Extract client information
        client_ip = self._get_client_ip(request)
        tenant_id = request.headers.get("X-Arkashri-Tenant", "default")
        user_id = request.headers.get("X-Arkashri-User-ID", "anonymous")
        endpoint = self._get_endpoint_category(request.url.path)
        
        # Check penalties first
        penalty_key = f"penalty:{client_ip}"
        if await self.backend.is_penalized(penalty_key):
            security_logger.log_permission_denied(
                user_id=user_id,
                resource="api",
                action="rate_limit_penalized"
            )
            
            raise HTTPException(
                status_code=429,
                detail="Rate limit penalty active. Please try again later.",
                headers={"Retry-After": "300"}
            )
        
        # Apply rate limits
        await self._check_rate_limits(
            request=client_ip,
            tenant_id=tenant_id,
            user_id=user_id,
            endpoint=endpoint
        )
        
        # Process request
        response = await call_next(request)
        
        # Adaptive rate limiting based on response time
        response_time = time.time() - start_time
        await self.adaptive_limiter.adjust_limits(endpoint, response_time)
        
        # Add rate limit headers
        self._add_rate_limit_headers(response)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request"""
        # Check for forwarded IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # Check for real IP
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to client IP
        return request.client.host if request.client else "unknown"
    
    def _get_endpoint_category(self, path: str) -> str:
        """Categorize endpoint for rate limiting"""
        if "/auth" in path or "/token" in path:
            return "auth"
        elif "/evidence" in path and "upload" in path:
            return "file_upload"
        elif any(heavy in path for heavy in ["/report", "/export", "/bulk"]):
            return "api_heavy"
        else:
            return "api_general"
    
    async def _check_rate_limits(
        self,
        request: str,
        tenant_id: str,
        user_id: str,
        endpoint: str
    ):
        """Check all applicable rate limits"""
        for rule_name, rule in self.rules:
            # Generate key based on scope
            if rule.scope == RateLimitScope.GLOBAL:
                key = f"rate_limit:global"
            elif rule.scope == RateLimitScope.TENANT:
                key = f"rate_limit:tenant:{tenant_id}"
            elif rule.scope == RateLimitScope.USER:
                key = f"rate_limit:user:{user_id}"
            elif rule.scope == RateLimitScope.IP:
                key = f"rate_limit:ip:{request}"
            elif rule.scope == RateLimitScope.ENDPOINT:
                key = f"rate_limit:endpoint:{endpoint}"
            else:
                continue
            
            # Adjust for adaptive limits
            if rule.scope == RateLimitScope.ENDPOINT:
                adjusted_requests = self.adaptive_limiter.get_adjusted_requests(
                    rule.requests, endpoint
                )
                rule.requests = adjusted_requests
            
            # Check rate limit
            result = await self.backend.check_rate_limit(key, rule)
            
            if not result.allowed:
                self.logger.warning(
                    "rate_limit_exceeded",
                    key=key,
                    rule_id=result.rule_id,
                    retry_after=result.retry_after,
                    endpoint=endpoint,
                    tenant_id=tenant_id,
                    user_id=user_id
                )
                
                security_logger.log_permission_denied(
                    user_id=user_id,
                    resource="api",
                    action="rate_limit_exceeded"
                )
                
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={
                        "X-RateLimit-Limit": str(rule.requests),
                        "X-RateLimit-Remaining": str(result.remaining),
                        "X-RateLimit-Reset": str(result.reset_time),
                        "Retry-After": str(result.retry_after) if result.retry_after else "60"
                    }
                )
    
    def _add_rate_limit_headers(self, response: Response):
        """Add rate limit information to response headers"""
        # This would be populated with actual rate limit info
        # For now, adding basic headers
        response.headers["X-RateLimit-Limit"] = "100"
        response.headers["X-RateLimit-Remaining"] = "99"
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.backend.disconnect()
