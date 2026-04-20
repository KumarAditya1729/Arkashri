# pyre-ignore-all-errors
import pytest
import pytest_asyncio
import asyncio

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
async def db_session(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from arkashri.db import Base
    
    db_path = tmp_path / "arkashri-test.db"
    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    
    # Clean state: drop everything first, then create
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        
    TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    async with TestSessionLocal() as session:
        yield session

    await test_engine.dispose()


@pytest_asyncio.fixture
async def test_session(db_session):
    """
    Alias for db_session — backward-compat for tests/test_data_governance.py
    and any other test that uses the older fixture name.
    """
    yield db_session
