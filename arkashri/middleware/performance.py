"""
Performance optimization middleware for production
Provides caching, compression, and request optimization
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import time
from typing import Dict, Optional, Tuple, Any
from urllib.parse import parse_qs, urlparse

import redis.asyncio as redis
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import structlog
import ujson

from arkashri.config import get_settings
from arkashri.logging_config import performance_logger

logger = structlog.get_logger(__name__)


class AdvancedCacheMiddleware(BaseHTTPMiddleware):
    """Advanced caching middleware with Redis backend"""
    
    def __init__(self, app, redis_url: str):
        super().__init__(app)
        self.settings = get_settings()
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None
        self.logger = structlog.get_logger("advanced_cache")
        
        # Cache configuration
        self.default_ttl = self.settings.cache_ttl
        self.cacheable_methods = {"GET", "HEAD", "OPTIONS"}
        self.cacheable_status_codes = {200, 301, 302, 304, 404}
        
        # Cache rules by endpoint pattern
        self.cache_rules = {
            "/api/v1/reporting": 300,      # 5 minutes
            "/api/v1/metrics": 60,        # 1 minute
            "/api/v1/workflow-pack": 3600, # 1 hour
            "/api/v1/jurisdictions": 3600, # 1 hour
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with caching"""
        # Only cache GET requests
        if request.method not in self.cacheable_methods:
            return await call_next(request)
        
        # Generate cache key
        cache_key = self._generate_cache_key(request)
        
        # Try to get from cache
        cached_response = await self._get_from_cache(cache_key)
        if cached_response:
            performance_logger.log_cache_operation("hit", cache_key, hit=True)
            return cached_response
        
        # Process request
        start_time = time.time()
        response = await call_next(request)
        processing_time = (time.time() - start_time) * 1000
        
        # Cache response if eligible
        if self._should_cache_response(request, response):
            await self._cache_response(cache_key, response, processing_time)
            performance_logger.log_cache_operation("set", cache_key)
        
        performance_logger.log_cache_operation("miss", cache_key, hit=False)
        return response
    
    def _generate_cache_key(self, request: Request) -> str:
        """Generate cache key for request"""
        # Include method, URL, and relevant query parameters
        url = str(request.url)
        
        # Sort query parameters for consistent keys
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        # Remove cache-busting parameters
        cache_busting_params = {"_", "cb", "v", "version", "timestamp"}
        filtered_params = {
            k: v for k, v in query_params.items() 
            if k.lower() not in cache_busting_params
        }
        
        # Create consistent query string
        sorted_params = sorted(filtered_params.items())
        query_string = "&".join(f"{k}={v[0]}" for k, v in sorted_params if v)
        
        # Build cache key
        cache_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if query_string:
            cache_url += f"?{query_string}"
        
        # Add tenant context if available
        tenant_id = request.headers.get("X-Arkashri-Tenant", "default")
        cache_url += f"|tenant:{tenant_id}"
        
        # Hash for shorter keys
        return f"cache:{hashlib.sha256(cache_url.encode()).hexdigest()}"
    
    async def _get_from_cache(self, cache_key: str) -> Optional[Response]:
        """Get response from cache"""
        if not self._redis:
            await self._connect_redis()
        
        try:
            cached_data = await self._redis.get(cache_key)
            if cached_data:
                # Parse cached response data
                data = ujson.loads(cached_data)
                
                # Reconstruct response
                response = JSONResponse(
                    content=data["content"],
                    status_code=data["status_code"],
                    headers=data["headers"]
                )
                
                # Add cache headers
                response.headers["X-Cache"] = "HIT"
                response.headers["X-Cache-Age"] = str(int(time.time()) - data["timestamp"])
                
                return response
        except Exception as e:
            self.logger.error("cache_get_error", key=cache_key, error=str(e))
        
        return None
    
    def _should_cache_response(self, request: Request, response: Response) -> bool:
        """Determine if response should be cached"""
        # Check status code
        if response.status_code not in self.cacheable_status_codes:
            return False
        
        # Check cache control headers
        cache_control = response.headers.get("Cache-Control", "")
        if "no-store" in cache_control or "private" in cache_control:
            return False
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("application/json"):
            return False
        
        # Check response size (don't cache very large responses)
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > 1024 * 1024:  # 1MB
            return False
        
        return True
    
    async def _cache_response(self, cache_key: str, response: Response, processing_time: float):
        """Cache response data"""
        if not self._redis:
            await self._connect_redis()
        
        try:
            # Determine TTL based on endpoint
            ttl = self._get_cache_ttl(request.url.path)
            
            # Prepare cache data
            cache_data = {
                "content": response.body.decode('utf-8') if hasattr(response, 'body') else {},
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "timestamp": time.time(),
                "processing_time_ms": processing_time
            }
            
            # Cache the response
            await self._redis.setex(
                cache_key,
                ttl,
                ujson.dumps(cache_data)
            )
            
        except Exception as e:
            self.logger.error("cache_set_error", key=cache_key, error=str(e))
    
    def _get_cache_ttl(self, path: str) -> int:
        """Get cache TTL for endpoint"""
        for pattern, ttl in self.cache_rules.items():
            if path.startswith(pattern):
                return ttl
        return self.default_ttl
    
    async def _connect_redis(self):
        """Connect to Redis"""
        if not self._redis:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
    
    async def cleanup(self):
        """Cleanup resources"""
        if self._redis:
            await self._redis.close()


class CompressionMiddleware(BaseHTTPMiddleware):
    """Enhanced compression middleware"""
    
    def __init__(self, app, min_size: int = 1024):
        super().__init__(app)
        self.min_size = min_size
        self.logger = structlog.get_logger("compression")
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Apply compression to responses"""
        # Check if client accepts gzip
        accept_encoding = request.headers.get("Accept-Encoding", "")
        if "gzip" not in accept_encoding.lower():
            return await call_next(request)
        
        response = await call_next(request)
        
        # Only compress if response is large enough and not already compressed
        content_length = response.headers.get("Content-Length")
        content_encoding = response.headers.get("Content-Encoding", "")
        
        if (content_encoding or 
            (content_length and int(content_length) < self.min_size)):
            return response
        
        # Compress response
        if hasattr(response, 'body') and response.body:
            compressed_body = gzip.compress(response.body)
            
            # Only use compressed version if it's smaller
            if len(compressed_body) < len(response.body):
                response.headers["Content-Encoding"] = "gzip"
                response.headers["Content-Length"] = str(len(compressed_body))
                response.body = compressed_body
                
                self.logger.info(
                    "response_compressed",
                    original_size=len(response.body),
                    compressed_size=len(compressed_body),
                    compression_ratio=len(compressed_body) / len(response.body)
                )
        
        return response


class RequestOptimizationMiddleware(BaseHTTPMiddleware):
    """Request optimization middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()
        self.logger = structlog.get_logger("request_optimization")
        
        # Track concurrent requests
        self.concurrent_requests = 0
        self.max_concurrent = self.settings.max_concurrent_requests
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Optimize request processing"""
        # Check concurrent request limit
        if self.concurrent_requests >= self.max_concurrent:
            self.logger.warning(
                "concurrent_request_limit_exceeded",
                current=self.concurrent_requests,
                max=self.max_concurrent
            )
            return JSONResponse(
                status_code=503,
                content={"error": "Service temporarily unavailable"}
            )
        
        self.concurrent_requests += 1
        start_time = time.time()
        
        try:
            # Add request timeout
            response = await asyncio.wait_for(
                call_next(request),
                timeout=self.settings.request_timeout
            )
            
            # Log performance metrics
            processing_time = (time.time() - start_time) * 1000
            performance_logger.log_request_duration(
                endpoint=request.url.path,
                method=request.method,
                processing_time_ms=processing_time,
                status_code=response.status_code
            )
            
            # Add performance headers
            response.headers["X-Response-Time"] = f"{processing_time:.2f}ms"
            response.headers["X-Concurrent-Requests"] = str(self.concurrent_requests)
            
            return response
            
        except asyncio.TimeoutError:
            self.logger.error(
                "request_timeout",
                path=request.url.path,
                timeout=self.settings.request_timeout
            )
            return JSONResponse(
                status_code=408,
                content={"error": "Request timeout"}
            )
        finally:
            self.concurrent_requests -= 1


class ConnectionPoolingMiddleware(BaseHTTPMiddleware):
    """Connection pooling and optimization middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.logger = structlog.get_logger("connection_pooling")
        
        # Track connection metrics
        self.active_connections = 0
        self.total_connections = 0
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Track and optimize connections"""
        self.active_connections += 1
        self.total_connections += 1
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Add connection headers
            response.headers["X-Connection-ID"] = str(self.total_connections)
            response.headers["X-Active-Connections"] = str(self.active_connections)
            
            return response
            
        finally:
            self.active_connections -= 1
            
            # Log connection metrics periodically
            if self.total_connections % 1000 == 0:
                self.logger.info(
                    "connection_metrics",
                    total=self.total_connections,
                    active=self.active_connections,
                    avg_time=(time.time() - start_time) * 1000
                )


class MemoryOptimizationMiddleware(BaseHTTPMiddleware):
    """Memory optimization and cleanup middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.logger = structlog.get_logger("memory_optimization")
        self.request_count = 0
        self.cleanup_interval = 1000
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Optimize memory usage"""
        self.request_count += 1
        
        # Process request
        response = await call_next(request)
        
        # Periodic cleanup
        if self.request_count % self.cleanup_interval == 0:
            await self._cleanup_memory()
        
        return response
    
    async def _cleanup_memory(self):
        """Perform memory cleanup"""
        try:
            # Force garbage collection
            import gc
            collected = gc.collect()
            
            self.logger.info(
                "memory_cleanup",
                objects_collected=collected,
                request_count=self.request_count
            )
            
        except Exception as e:
            self.logger.error("memory_cleanup_error", error=str(e))
