import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_arkashri.db"

import asyncio
from fastapi.testclient import TestClient
from arkashri.main import app
from arkashri.dependencies import require_api_client, AuthContext
from arkashri.models import ClientRole

# Override the auth dependency to return a mock admin
async def mock_auth(*args, **kwargs):
    return AuthContext(
        tenant_id="default_tenant",
        user_id="user-xyz",
        role=ClientRole.ADMIN,
        token="mock",
        is_service_account=False
    )

app.dependency_overrides[require_api_client] = lambda roles: mock_auth

client = TestClient(app)

response = client.post(
    "/api/v1/engagements/engagements",
    json={
        "client_name": "Mehta Textiles Ltd",
        "engagement_type": "FINANCIAL_AUDIT",
        "jurisdiction": "IN",
        "tenant_id": "default_tenant"
    }
)

print(response.status_code)
print(response.text)
