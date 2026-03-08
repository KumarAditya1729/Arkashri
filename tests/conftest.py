import pytest_asyncio
from unittest.mock import AsyncMock, patch

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
