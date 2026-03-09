import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, patch

@pytest.fixture(scope="session", autouse=True)
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# Ensure all models are registered
import arkashri.models
import arkashri.routers.risks    # contains RiskEntry
import arkashri.routers.evidence # contains EvidenceRecord

@pytest_asyncio.fixture
async def mock_redis():
    with patch("arkashri.services.risk_engine.cache_get", new_callable=AsyncMock) as mock_get, \
         patch("arkashri.services.risk_engine.cache_set", new_callable=AsyncMock) as mock_set:
        mock_get.return_value = None
        mock_set.return_value = None
        yield {"get": mock_get, "set": mock_set}

@pytest_asyncio.fixture
async def mock_session():
    session = AsyncMock()
    # Mock the scalar / scalars chaining behavior
    session.scalar.return_value = None
    session.scalars.return_value = []
    return session
@pytest_asyncio.fixture
async def async_client(db_session):
    from httpx import AsyncClient, ASGITransport
    from arkashri.main import app
    from arkashri.db import get_session
    
    # Override get_session to use the test db_session
    async def _get_session_override():
        yield db_session
        
    app.dependency_overrides[get_session] = _get_session_override
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
        
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def db_session():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from arkashri.config import get_settings
    from arkashri.db import Base
    
    settings = get_settings()
    # Create fresh engine for this test function to avoid loop conflicts
    # Using a pool size of 1 for tests to minimize resource usage
    test_engine = create_async_engine(settings.database_url)
    
    # Clean state: drop everything first, then create
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        
    TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    async with TestSessionLocal() as session:
        yield session
        
    await test_engine.dispose()
