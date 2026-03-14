# pyre-ignore-all-errors
from fastapi.testclient import TestClient

from arkashri.main import app


client = TestClient(app)



def test_workflow_pack_index_endpoint() -> None:
    response = client.get("/api/v1/workflow-pack")

    assert response.status_code == 200
    data = response.json()
    assert data["pack_id"] == "arkashri_audit_workflow_pack"
    assert len(data["templates"]) == 14



def test_workflow_pack_template_endpoint() -> None:
    response = client.get("/api/v1/workflow-pack/financial_audit")

    assert response.status_code == 200
    data = response.json()
    assert data["audit_type"] == "financial_audit"
    assert data["template"]["workflow_id"] == "financial_audit_v1"



def test_workflow_pack_template_not_found() -> None:
    response = client.get("/api/v1/workflow-pack/unknown_audit_type")

    assert response.status_code == 404
