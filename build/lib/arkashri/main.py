from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from arq import create_pool
from arq.connections import RedisSettings

import uuid
import structlog

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from prometheus_fastapi_instrumentator import Instrumentator
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
import redis.asyncio as redis_async
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from arkashri.config import get_settings
from arkashri.routers import router as api_v1_router
from arkashri.dependencies import limiter

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

settings = get_settings()

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=settings.sentry_traces_sample_rate if settings.enable_performance_monitoring else 0.0,
        environment=settings.app_env,
    )

# ── OpenTelemetry setup ───────────────────────────────────────────────────────
resource  = Resource.create({"service.name": "arkashri-decision-engine"})
provider  = TracerProvider(resource=resource)
processor = BatchSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger("api")


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Parse REDIS_URL: redis://host:port/db  →  host + port
    redis_url = settings.redis_url  # e.g. redis://redis:6379/0
    try:
        parts = redis_url.replace("redis://", "").split(":")
        redis_host = parts[0]
        redis_port = int(parts[1].split("/")[0]) if len(parts) > 1 else 6379
        
        # Initialize ARQ Pool
        app.state.redis_pool = await create_pool(
            RedisSettings(host=redis_host, port=redis_port)
        )
        logger.info("Connected to Redis ARQ pool", host=redis_host, port=redis_port)
        
        # Initialize FastAPI Cache
        cache_redis = redis_async.from_url(redis_url, encoding="utf-8", decode_responses=False)
        FastAPICache.init(RedisBackend(cache_redis), prefix="arkashri-cache")
        logger.info("Initialized FastAPI Cache with Redis backend")
        
    except Exception as e:
        logger.warning("Failed to connect to Redis (ARQ/Cache will be unavailable)", error=str(e))
        app.state.redis_pool = None

    yield

    redis_pool = getattr(app.state, "redis_pool", None)
    if redis_pool is not None:
        redis_pool.close()
        await redis_pool.wait_closed()
        logger.info("Closed Redis ARQ pool")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Arkashri Deterministic Decision Engine",
    version="2.0.0",
    description="Deterministic, replayable, and auditable financial decision core",
    lifespan=lifespan,
)

# Initialize Rate Limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── Health endpoint (used by docker-compose healthcheck) ─────────────────────
@app.get("/health", include_in_schema=False)
async def health():
    """
    Liveness + readiness probe.
    Returns 200 OK with status of DB and Redis connections.
    """
    from arkashri.db import engine
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    redis_ok = getattr(app.state, "redis_pool", None) is not None

    status = "healthy" if (db_ok and redis_ok) else "degraded"
    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={
            "status":  status,
            "db":      "ok" if db_ok else "unreachable",
            "redis":   "ok" if redis_ok else "unreachable",
            "version": "2.0.0",
        },
    )

app.include_router(api_v1_router, prefix="/api/v1")

# ── Instrumentation & Metrics ──────────────────────────────────────────────────
FastAPIInstrumentor.instrument_app(app)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


class StructlogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        span      = trace.get_current_span()
        trace_id  = format(span.get_span_context().trace_id, "032x") if span.is_recording() else "none"
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        tenant_id  = request.headers.get("X-Arkashri-Tenant", "unknown_tenant")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id, request_id=request_id,
            tenant_id=tenant_id, path=request.url.path, method=request.method,
        )
        log = structlog.get_logger("api")
        log.info("request_started")
        try:
            response = await call_next(request)
            log.info("request_finished", status_code=response.status_code)
            return response
        except Exception as e:
            log.exception("request_failed", error=str(e))
            raise

app.add_middleware(StructlogMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key, max_age=86400)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173", "http://localhost:5173",
        "http://127.0.0.1:4173", "http://localhost:4173",
        "http://localhost:3000",  "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
