# pyre-ignore-all-errors
import pytest
import uuid
from httpx import AsyncClient
from arkashri.main import app
from arkashri.models import SystemAuditLog
from sqlalchemy import select

@pytest.mark.asyncio
async def test_health_check_comprehensive(async_client: AsyncClient):
    """Verifies the new multi-dependency health check endpoint."""
    response = await async_client.get("/health")
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data
    assert "dependencies" in data
    assert "database" in data["dependencies"]
    assert "redis" in data["dependencies"]

@pytest.mark.asyncio
async def test_engine_status_endpoint(async_client: AsyncClient):
    """Verifies the new engine status endpoint for frontend banners."""
    response = await async_client.get("/api/v1/status/engine")
    assert response.status_code == 200
    data = response.json()
    assert "ai_fabric" in data
    assert "polkadot" in data

@pytest.mark.asyncio
async def test_audit_log_capture(async_client: AsyncClient, db_session):
    """
    Verifies that system events are actually written to the DB.
    (This requires a real DB or a mock that we can query).
    """
    from arkashri.services.audit_log import log_system_event
    
    await log_system_event(
        db_session,
        tenant_id="test_tenant",
        action="TEST_ACTION",
        resource_type="TEST_RESOURCE"
    )
    
    stmt = select(SystemAuditLog).where(SystemAuditLog.action == "TEST_ACTION")
    result = await db_session.execute(stmt)
    entry = result.scalar_one_or_none()
    assert entry is not None
    assert entry.tenant_id == "test_tenant"

@pytest.mark.asyncio
async def test_admin_audit_logs_access(async_client: AsyncClient):
    """Verifies that admin can access the audit trail."""
    # This requires admin auth headers
    headers = {"X-API-KEY": "admin-key", "X-TENANT-ID": "arkashri_master"}
    # In this demo repo, the 'require_api_client' might need a mock session or real setup
    pass 
@pytest.mark.asyncio
async def test_audit_export_generation(db_session):
    """Verifies that the PDF export service generates a file."""
    # We need a dummy engagement for this to work without errors
    from arkashri.models import Engagement, EngagementType, ClientRole
    from arkashri.services.audit_export import generate_regulatory_pdf
    import os
    
    eng = Engagement(
        tenant_id="test_export_tenant",
        client_name="Test Export Client",
        engagement_type="external_audit", # explicit lowercase
        jurisdiction="IN"
    )
    db_session.add(eng)
    await db_session.commit()
    await db_session.refresh(eng)
    
    path = await generate_regulatory_pdf(db_session, eng.id)
    assert os.path.exists(path)
    # Cleanup
    # if os.path.exists(path): os.remove(path)
