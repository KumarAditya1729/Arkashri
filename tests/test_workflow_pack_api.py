# pyre-ignore-all-errors
from fastapi.testclient import TestClient

from arkashri.main import app


client = TestClient(app)



def test_workflow_pack_index_endpoint() -> None:
    response = client.get("/api/v1/workflow-pack")

    assert response.status_code == 200
    data = response.json()
    assert data["pack_id"] == "arkashri_audit_workflow_pack"
    assert len(data["templates"]) >= 14



def test_workflow_pack_template_endpoint() -> None:
    response = client.get("/api/v1/workflow-pack/financial_audit")

    assert response.status_code == 200
    data = response.json()
    assert data["audit_type"] == "financial_audit"
    assert data["template"]["workflow_id"] == "financial_audit_v1"


def test_workflow_pack_service_catalog_endpoint() -> None:
    response = client.get("/api/v1/workflow-pack/service-catalog")

    assert response.status_code == 200
    data = response.json()
    assert data["catalog_id"] == "arkashri_big4_audit_service_catalog"
    assert data["division_count"] >= 5
    assert data["service_count"] >= 80
    service_ids = {
        service["id"]
        for division in data["divisions"]
        for service in division["services"]
    }
    assert {"ai_audit", "soc_2_audit", "statutory_audit", "forensic_audit"} <= service_ids
    readiness_values = {
        service["readiness"]
        for division in data["divisions"]
        for service in division["services"]
    }
    assert "specialist_build_needed" not in readiness_values
    assert "specialist_engine_ready" in readiness_values


def test_workflow_pack_master_lifecycle_endpoint() -> None:
    response = client.get("/api/v1/workflow-pack/master-lifecycle")

    assert response.status_code == 200
    data = response.json()
    assert data["lifecycle_id"] == "arkashri_master_audit_lifecycle"
    assert data["phase_count"] == 12
    assert data["specialized_overlay_count"] >= 7
    assert data["phases"][0]["phase_id"] == "engagement_acceptance"
    assert "AI anomaly detection" in data["modern_ai_driven_workflow"]



def test_workflow_pack_template_not_found() -> None:
    response = client.get("/api/v1/workflow-pack/unknown_audit_type")

    assert response.status_code == 404
