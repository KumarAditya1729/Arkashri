# pyre-ignore-all-errors
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from arkashri.db import get_session
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from arq import create_pool
from arq.connections import RedisSettings

import os
import uuid
import structlog
import asyncio

# ── Conditional heavy imports (skip on low-resource envs to save RAM) ─────────
# OpenTelemetry — only if ENABLE_TRACING=true
if os.getenv("ENABLE_TRACING", "false").lower() == "true":
    from opentelemetry import trace as _otel_trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    _TRACING_ENABLED = True
else:
    _TRACING_ENABLED = False

# Prometheus — only if ENABLE_METRICS=true
if os.getenv("ENABLE_METRICS", "false").lower() == "true":
    from prometheus_fastapi_instrumentator import Instrumentator
    _METRICS_ENABLED = True
else:
    _METRICS_ENABLED = False

from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
import redis.asyncio as redis_async
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from arkashri.config import get_settings
from arkashri.routers import router as api_v1_router
from arkashri.routers.websockets import router as websockets_router
from arkashri.routers.admin import router as admin_router
from arkashri.dependencies import limiter
from arkashri.middleware.idempotency import IdempotencyMiddleware

# Import production middleware
from arkashri.middleware.security import (
    SecurityHeadersMiddleware,
    RequestValidationMiddleware,
    ThreatDetectionMiddleware,
    RequestSizeMiddleware
)
from arkashri.middleware.rate_limiting import ProductionRateLimitMiddleware
from arkashri.middleware.performance import (
    AdvancedCacheMiddleware,
    CompressionMiddleware,
    RequestOptimizationMiddleware,
    ConnectionPoolingMiddleware,
    MemoryOptimizationMiddleware
)

# Import production services
from arkashri.logging_config import setup_logging, security_logger, performance_logger
from arkashri.utils.error_handling import error_handler, ErrorContext
from arkashri.db import db_manager
from arkashri.services.backup import disaster_recovery_service

# Sentry — only if DSN is configured
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

settings = get_settings()

# Setup production logging
setup_logging()
logger = structlog.get_logger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=settings.sentry_traces_sample_rate if settings.enable_performance_monitoring else 0.0,
        environment=settings.app_env,
    )

# ── OpenTelemetry setup (only if ENABLE_TRACING=true) ────────────────────────
if _TRACING_ENABLED:
    resource  = Resource.create({"service.name": "arkashri-decision-engine"})
    provider  = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    _otel_trace.set_tracer_provider(provider)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Parse REDIS_URL: redis://host:port/db  →  host + port
    redis_url = settings.redis_url  # e.g. redis://default:pass@redis:6379/0
    redis_pool = None
    if redis_url:
        import urllib.parse
        parsed = urllib.parse.urlparse(redis_url)
        redis_host = parsed.hostname or "localhost"
        redis_port = parsed.port or 6379
        
        try:
            app.state.redis_pool = await create_pool(
                RedisSettings(host=redis_host, port=redis_port)
            )
            logger.info("Connected to Redis ARQ pool", host=redis_host, port=redis_port)
            
            # Initialize FastAPI Cache
            cache_redis = redis_async.from_url(redis_url, encoding="utf-8", decode_responses=False)
            FastAPICache.init(RedisBackend(cache_redis), prefix="arkashri-cache")
            logger.info("Initialized FastAPI Cache with Redis backend")
            
            # Initialize database health checker
            await db_manager.health_checker.check_health()
            logger.info("Database health checker initialized")
            
            # Start background tasks for production
            if settings.backup_enabled:
                asyncio.create_task(backup_scheduler())
            
            if settings.enable_performance_metrics:
                asyncio.create_task(metrics_collector())
            
        except Exception as e:
            logger.warning("Failed to connect to Redis (ARQ/Cache will be unavailable)", error=str(e))
            app.state.redis_pool = None
            # Ensure FastAPICache is always initialized to prevent AssertionError on cached routes
            try:
                from fastapi_cache.backends.inmemory import InMemoryBackend
                FastAPICache.init(InMemoryBackend(), prefix="arkashri-cache")
                logger.info("Initialized FastAPI Cache with InMemory fallback (Redis unavailable)")
            except Exception as cache_err:
                logger.warning("FastAPICache init fallback also failed", error=str(cache_err))

    yield

    redis_pool = getattr(app.state, "redis_pool", None)
    if redis_pool is not None:
        await redis_pool.close()
        logger.info("Closed Redis ARQ pool")

    # Gracefully disconnect the SQLAlchemy pool on shutdown
    try:
        from arkashri.db import engine
        await engine.dispose()
        logger.info("Disposed SQLAlchemy connection pool")
    except Exception as e:
        logger.warning("Error disposing engine", error=str(e))
    
    # Cleanup middleware resources
    await cleanup_middleware_resources(app)


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Arkashri Deterministic Decision Engine",
    version="2.0.0",
    description="Deterministic, replayable, and auditable financial decision core",
    lifespan=lifespan,
)

# ── Production Middleware Stack ─────────────────────────────────────────────────
# Enhanced security middleware
from arkashri.middleware.oauth2 import create_oauth2_middleware
from arkashri.middleware.mfa import create_mfa_middleware
from arkashri.middleware.enhanced_security import create_enhanced_security_middleware
# Security middleware (WebSocket-friendly configuration)
# app.add_middleware(SecurityHeadersMiddleware)  # Temporarily disabled due to import issue

# Enhanced security features
oauth2_middleware = create_oauth2_middleware(app)
if oauth2_middleware:
    app.add_middleware(type(oauth2_middleware))

mfa_middleware = create_mfa_middleware(app)
if mfa_middleware:
    app.add_middleware(type(mfa_middleware))

enhanced_security_middleware = create_enhanced_security_middleware(app)
if enhanced_security_middleware:
    app.add_middleware(type(enhanced_security_middleware))
# app.add_middleware(RequestSizeMiddleware)  # Disabled for WebSocket compatibility
# app.add_middleware(RequestValidationMiddleware)  # Disabled for WebSocket compatibility
# app.add_middleware(ThreatDetectionMiddleware)  # Disabled for WebSocket compatibility

# Rate limiting and throttling - Disabled for WebSocket compatibility
# if settings.redis_url:
#     app.add_middleware(ProductionRateLimitMiddleware, redis_url=settings.redis_url)

# Performance optimization - WebSocket-friendly
if settings.redis_url:
    app.add_middleware(AdvancedCacheMiddleware, redis_url=settings.redis_url)
app.add_middleware(CompressionMiddleware)
# app.add_middleware(RequestOptimizationMiddleware)  # Disabled for WebSocket compatibility
# app.add_middleware(ConnectionPoolingMiddleware)  # Disabled for WebSocket compatibility
# app.add_middleware(MemoryOptimizationMiddleware)  # Disabled for WebSocket compatibility

# Core middleware - WebSocket-friendly
# app.add_middleware(
#     IdempotencyMiddleware, 
#     redis_client_getter=lambda: redis_async.from_url(settings.redis_url)
# )
# app.add_middleware(
#     TrustedHostMiddleware, 
#     allowed_hosts=[host.strip() for host in settings.allowed_hosts.split(",")] if hasattr(settings, "allowed_hosts") and settings.allowed_hosts else ["*"]
# )

if settings.enable_compression:
    app.add_middleware(GZipMiddleware, minimum_size=1000)

# Initialize Rate Limiting - Disabled for WebSocket compatibility
# app.state.limiter = limiter
# app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# app.add_middleware(SlowAPIMiddleware)

# Session middleware - WebSocket-friendly
# app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key, max_age=86400)

# CORS middleware (WebSocket-friendly)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Background Tasks ──────────────────────────────────────────────────────────
async def backup_scheduler():
    """Background task for scheduled backups"""
    while True:
        try:
            await asyncio.sleep(86400)  # Run daily
            
            if settings.backup_enabled:
                logger.info("starting_scheduled_backup")
                backups = await disaster_recovery_service.create_full_backup()
                logger.info("scheduled_backup_completed", backups=len(backups))
                
                # Clean up old backups
                await disaster_recovery_service.db_backup.cleanup_old_backups()
                
        except Exception as e:
            logger.error("backup_scheduler_error", error=str(e))


async def metrics_collector():
    """Background task for metrics collection"""
    while True:
        try:
            await asyncio.sleep(60)  # Collect every minute
            
            if settings.enable_performance_metrics:
                # Collect database metrics
                db_stats = await db_manager.get_connection_stats()
                logger.info("database_metrics", **db_stats)
                
                # Log performance metrics
                performance_logger.log_cache_operation("collect", "system_metrics")
                
        except Exception as e:
            logger.error("metrics_collector_error", error=str(e))


async def cleanup_middleware_resources(app: FastAPI):
    """Cleanup middleware resources"""
    try:
        # Cleanup rate limiting middleware
            # Skip for now to avoid instance/class attribute issues during rapid restarts
            pass
    except Exception as e:
        logger.warning("middleware_cleanup_error", error=str(e))


# ── Enhanced Health endpoint ─────────────────────────────────────────────────
from arkashri.services.health import get_full_health_status
from arkashri.routers.engine_status import router as status_router

@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint"""
    return {
        "app": "Arkashri Audit OS",
        "version": "1.0.0",
        "status": "active",
        "message": "API is running"
    }

@app.get("/health", include_in_schema=False)
async def health(db: AsyncSession = Depends(get_session)):
    """
    Comprehensive liveness + readiness probe with production metrics
    """
    health_status = await get_full_health_status(db)
    
    # Add production metrics
    health_status.update({
        "database_stats": await db_manager.get_connection_stats(),
        "middleware_status": {
            "rate_limiting": bool(app.state.redis_pool),
            "cache": bool(app.state.redis_pool),
            "compression": settings.enable_compression,
        }
    })
    
    return JSONResponse(
        status_code=503 if health_status["status"] == "unhealthy" else 200,
        content=health_status,
    )


@app.get("/readyz", include_in_schema=False)
async def readyz():
    """
    Lightweight readiness probe — returns 200 only when DB is reachable.
    Used by Railway / Kubernetes to gate traffic during startup.
    """
    try:
        from arkashri.db import AsyncSessionLocal
        from sqlalchemy import text
        from arkashri.config import get_settings
        settings = get_settings()
        raw_url = settings.database_url
        if "@" in raw_url:
            masked_url = raw_url.split(":")[0] + "://***:***@" + raw_url.split("@")[-1]
        else:
            masked_url = raw_url[:10] + "...(no @ found)"
            
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
            return JSONResponse(status_code=200, content={"ready": True, "db": "ok", "url": masked_url})
    except Exception as e:
        import traceback
        from arkashri.config import get_settings
        settings = get_settings()
        raw_url = settings.database_url
        masked_url = raw_url.split(":")[0] + "://***:***@" + raw_url.split("@")[-1] if "@" in raw_url else raw_url[:15] + "...(no @)"
        logger.warning("readyz_db_unreachable", error=str(e))
        return JSONResponse(status_code=503, content={"ready": False, "db": "unreachable", "detail": str(e), "url": masked_url, "trace": traceback.format_exc()})


# ── Enhanced Metrics endpoint ───────────────────────────────────────────────
@app.get("/metrics/detailed", include_in_schema=False)
async def detailed_metrics():
    """Detailed production metrics"""
    try:
        db_stats = await db_manager.get_connection_stats()
        
        return JSONResponse({
            "database": db_stats,
            "settings": {
                "environment": settings.app_env,
                "auth_enforced": settings.auth_enforced,
                "backup_enabled": settings.backup_enabled,
                "performance_monitoring": settings.enable_performance_metrics,
            },
            "middleware": {
                "rate_limiting": bool(app.state.redis_pool),
                "cache": bool(app.state.redis_pool),
                "compression": settings.enable_compression,
            }
        })
    except Exception as e:
        logger.error("metrics_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to collect metrics"}
        )


# ── Router Registration ───────────────────────────────────────────────────────
from arkashri.routers.standards import router as standards_router
from arkashri.routers.judgments import router as judgments_router
from arkashri.routers.client_portal import router as client_portal_router
from arkashri.routers.reporting import router as reporting_router

app.include_router(api_v1_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(status_router, prefix="/api/v1")
app.include_router(reporting_router, prefix="/api/v1")
app.include_router(standards_router, prefix="/api")
app.include_router(judgments_router, prefix="/api")
app.include_router(client_portal_router, prefix="/api")
app.include_router(websockets_router)

# Add WebSocket endpoint directly for testing
@app.websocket("/ws/direct")
async def direct_websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_text("Direct WebSocket connection successful!")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")
    except Exception as e:
        print(f"Direct WebSocket error: {e}")

# ── Instrumentation & Metrics ──────────────────────────────────────────────────
# Temporarily disabled for WebSocket testing
# FastAPIInstrumentor.instrument_app(app)
# Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ── Request ID Middleware ───────────────────────────────────────────────────
# Temporarily disabled for WebSocket testing
# class RequestIDMiddleware(BaseHTTPMiddleware):
#     async def dispatch(self, request: Request, call_next):
#         if settings.enable_request_id:
#             request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
#             request.state.request_id = request_id
#             
#             # Add to response headers
#             response = await call_next(request)
#             response.headers["X-Request-ID"] = request_id
#             return response
#         
#         return await call_next(request)

# if settings.enable_request_id:
#     app.add_middleware(RequestIDMiddleware)


# ── Structured Logging Middleware ───────────────────────────────────────────
# Temporarily disabled for WebSocket testing
# class StructlogMiddleware(BaseHTTPMiddleware):
#     async def dispatch(self, request: Request, call_next):
#         span      = trace.get_current_span()
#         trace_id  = format(span.get_span_context().trace_id, "032x") if span.is_recording() else "none"
#         request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
#         tenant_id  = request.headers.get("X-Arkashri-Tenant", "unknown_tenant")

#         structlog.contextvars.clear_contextvars()
#         structlog.contextvars.bind_contextvars(
#             trace_id=trace_id, 
#             request_id=request_id,
#             tenant_id=tenant_id, 
#             path=request.url.path, 
#             method=request.method,
#         )
#         log = structlog.get_logger("api")
#         log.info("request_started")
#         try:
#             response = await call_next(request)
#             log.info("request_finished", status_code=response.status_code)
#             return response
#         except Exception as e:
#             log.exception("request_failed", error=str(e))
#             raise

# app.add_middleware(StructlogMiddleware)
# Fixed AsyncSession import issue
