# pyre-ignore-all-errors
from collections.abc import AsyncGenerator
import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
import structlog

from arkashri.config import get_settings
from arkashri.utils.error_handling import database_retry, DatabaseException

logger = structlog.get_logger(__name__)


class Base(DeclarativeBase):
    pass


settings = get_settings()

# Production-ready engine configuration
# Neon PostgreSQL (serverless) — small pool, fast timeout, pooler-compatible
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=min(settings.db_pool_size, 5),     # Neon free tier: max 10 connections
    max_overflow=min(settings.db_max_overflow, 5),
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=300,    # 5 min — Neon drops idle connections at ~5 min
    echo=settings.db_echo,
    connect_args={
        "command_timeout": 10,        # Fail fast — don't block worker for 30s
        "statement_cache_size": 0,    # Required for Neon/PgBouncer connection pooler
        "server_settings": {
            "application_name": "arkashri_api",
            "jit": "off",             # Disable JIT for faster simple queries
        }
    } if "postgresql" in settings.database_url else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    autoflush=False, 
    autocommit=False, 
    expire_on_commit=False
)


class DatabaseHealthChecker:
    """Database health monitoring and connection validation"""
    
    def __init__(self):
        self.logger = structlog.get_logger("db_health")
        self._last_check: Optional[float] = None
        self._is_healthy: bool = True
        self._check_interval = settings.health_check_interval
    
    async def check_health(self) -> bool:
        """Check database connectivity and performance"""
        try:
            async with AsyncSessionLocal() as session:
                # Simple health check query
                await session.execute(text("SELECT 1 as health_check"))
                await session.commit()

                self._is_healthy = True
                self._last_check = asyncio.get_running_loop().time()  # deprecated get_event_loop() fix

                self.logger.info(
                    "database_health_check_success",
                    timestamp=self._last_check
                )
                return True

        except Exception as e:
            self._is_healthy = False
            self._last_check = asyncio.get_running_loop().time()  # deprecated get_event_loop() fix
            self.logger.error(
                "database_health_check_failed",
                error=str(e),
                timestamp=self._last_check
            )
            return False
        # Removed unreachable `return False` (dead code after explicit returns in both branches)
    
    def is_healthy(self) -> bool:
        """Check if database is currently healthy"""
        last = self._last_check
        if last is None:
            return False

        try:
            current_time = asyncio.get_running_loop().time()  # deprecated get_event_loop() fix
        except RuntimeError:
            # No running loop (called from sync context) — use monotonic as fallback
            import time
            current_time = time.monotonic()
        time_since_check = current_time - last
        return self._is_healthy and time_since_check < self._check_interval
    
    async def wait_for_healthy(self, timeout: int = 30) -> bool:
        """Wait for database to become healthy"""
        loop = asyncio.get_running_loop()  # deprecated get_event_loop() fix
        start_time = loop.time()

        while (loop.time() - start_time) < timeout:
            if await self.check_health():
                return True
            await asyncio.sleep(1)

        return False


class DatabaseManager:
    """Advanced database management with connection monitoring"""
    
    def __init__(self):
        self.health_checker = DatabaseHealthChecker()
        self.logger = structlog.get_logger("db_manager")
    
    @database_retry(max_attempts=3)
    async def execute_with_retry(
        self, 
        query: str, 
        params: Optional[dict] = None,
        session: Optional[AsyncSession] = None
    ):
        """Execute database query with retry logic"""
        if session is None:
            async with AsyncSessionLocal() as session:
                return await self._execute_query(session, query, params)
        else:
            return await self._execute_query(session, query, params)
    
    async def _execute_query(
        self, 
        session: AsyncSession, 
        query: str, 
        params: Optional[dict] = None
    ):
        """Internal query execution with logging"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            if params:
                result = await session.execute(text(query), params)
            else:
                result = await session.execute(text(query))
            
            duration = (asyncio.get_event_loop().time() - start_time) * 1000
            
            # Log performance metrics
            from arkashri.logging_config import performance_logger
            performance_logger.log_database_query(
                query=query,
                duration_ms=duration,
                rows_affected=result.rowcount if hasattr(result, 'rowcount') else None
            )
            
            return result
            
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start_time) * 1000
            
            self.logger.error(
                "database_query_failed",
                query_hash=hash(query) % 10000,
                duration_ms=duration,
                error=str(e)
            )
            
            raise DatabaseException(
                message=f"Database query failed: {str(e)}",
                cause=e
            )
    
    async def get_connection_stats(self) -> dict:
        """Get database connection pool statistics"""
        pool = engine.pool
        
        return {
            "pool_size": pool.size() if hasattr(pool, "size") else 0,
            "checked_in": pool.checkedin() if hasattr(pool, "checkedin") else 0,
            "checked_out": pool.checkedout() if hasattr(pool, "checkedout") else 0,
            "overflow": pool.overflow() if hasattr(pool, "overflow") else 0,
            "invalidated": pool.invalidated() if hasattr(pool, "invalidated") else 0,
            "is_healthy": self.health_checker.is_healthy(),
        }
    
    async def close_connections(self):
        """Gracefully close all database connections"""
        self.logger.info("closing_database_connections")
        await engine.dispose()


# Global database manager instance
db_manager = DatabaseManager()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Enhanced session dependency with health checking"""
    # Ensure database is healthy before providing session
    if not db_manager.health_checker.is_healthy():
        # H-NEW-6: Only re-check health if at least 5 seconds passed since last failure
        # to prevent health-check-storming the DB.
        now = asyncio.get_event_loop().time()
        last = db_manager.health_checker._last_check or 0
        if now - last > 5.0:
            await db_manager.health_checker.check_health()
        
        if not db_manager.health_checker.is_healthy():
            raise DatabaseException("Database is not healthy")
    
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_read_replica_session() -> AsyncGenerator[AsyncSession, None]:
    """Session for read replicas (if configured in future)"""
    # For now, same as get_session, but can be extended for read replicas
    async for session in get_session():
        yield session
