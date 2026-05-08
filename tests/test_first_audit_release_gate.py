# pyre-ignore-all-errors
from __future__ import annotations

import pytest


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
    b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.asyncio
async def test_first_audit_release_gate_happy_path(async_client, monkeypatch) -> None:
    """
    CA demo release gate: a real engagement must move through the first-audit
    path on persisted backend records, including AI governance and seal lock.
    """
    monkeypatch.setattr("arkashri.dependencies.settings.auth_enforced", False)

    tenant = "first_audit_gate"
    headers = {"X-Arkashri-Tenant": tenant}

    created = await async_client.post(
        "/api/v1/engagements/engagements",
        headers=headers,
        json={
            "tenant_id": "attacker_supplied_tenant",
            "jurisdiction": "IN",
            "client_name": "CA Demo First Audit Private Limited",
            "engagement_type": "STATUTORY_AUDIT",
            "auditType": "statutory_audit",
            "independence_cleared": True,
            "kyc_cleared": True,
            "conflict_check_notes": "CA demo independence and KYC verified.",
        },
    )
    assert created.status_code == 201, created.text
    engagement = created.json()
    engagement_id = engagement["id"]
    assert engagement["tenant_id"] == tenant

    workspace = await async_client.post(
        f"/api/v1/standards/engagements/{engagement_id}/india-workspace/bootstrap",
        headers=headers,
    )
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["sections"] >= 1

    phase = await async_client.post(
        f"/api/v1/engagements/{engagement_id}/phases",
        headers=headers,
        json={"name": "Planning", "status": "IN_PROGRESS", "owner": "Engagement Partner", "progress": 25},
    )
    assert phase.status_code == 201, phase.text

    team = await async_client.post(
        f"/api/v1/engagements/{engagement_id}/team",
        headers=headers,
        json={"name": "Asha Rao", "role": "Engagement Partner", "initials": "AR", "color": "blue"},
    )
    assert team.status_code == 201, team.text

    materiality = await async_client.post(
        f"/api/v1/engagements/engagements/{engagement_id}/materiality",
        headers=headers,
        json={
            "basis": "REVENUE",
            "basis_amount": 10_000_000,
            "overall_percentage": 5,
            "performance_percentage": 75,
            "trivial_threshold_percentage": 5,
            "notes": "First-audit smoke materiality benchmark.",
        },
    )
    assert materiality.status_code == 201, materiality.text

    risk = await async_client.post(
        f"/api/v1/engagements/{engagement_id}/risks",
        headers=headers,
        json={
            "title": "Revenue recognition cut-off risk",
            "area": "Revenue",
            "likelihood": "HIGH",
            "impact": "HIGH",
            "owner": "Engagement Partner",
        },
    )
    assert risk.status_code == 201, risk.text
    risk_id = risk.json()["id"]

    control = await async_client.post(
        f"/api/v1/engagements/{engagement_id}/controls",
        headers=headers,
        json={
            "title": "Review sales cut-off after period end",
            "area": "Revenue",
            "control_type": "DETECTIVE",
            "frequency": "Annual",
            "owner": "Engagement Partner",
            "risk_id": risk_id,
        },
    )
    assert control.status_code == 201, control.text
    control_id = control.json()["id"]

    tested = await async_client.patch(
        f"/api/v1/engagements/{engagement_id}/controls/{control_id}",
        headers=headers,
        json={"status": "EFFECTIVE"},
    )
    assert tested.status_code == 200, tested.text
    assert tested.json()["last_tested"]

    evidence = await async_client.post(
        f"/api/v1/engagements/{engagement_id}/evidence",
        headers=headers,
        files={"file": ("sales-cutoff.png", PNG_1X1, "image/png")},
        data={"test_ref": "REV-CUT-001"},
    )
    assert evidence.status_code == 201, evidence.text

    ai_log = await async_client.post(
        "/api/v1/usas/ai-governance-logs",
        headers=headers,
        json={
            "tenant_id": "attacker_supplied_tenant",
            "jurisdiction": "IN",
            "decision_id": f"{engagement_id}:planning",
            "model_used": "GPT-4o",
            "decision_rationale": (
                "Source binding: SA 315 risk identification; CA reviewed revenue "
                "cut-off risk and agreed to proceed with targeted procedures."
            ),
            "human_override": True,
            "override_reason": "CA accepted the recommendation after source review.",
        },
    )
    assert ai_log.status_code == 201, ai_log.text
    assert ai_log.json()["tenant_id"] == tenant

    workflow = await async_client.patch(
        f"/api/v1/engagements/engagements/{engagement_id}/workflow",
        headers=headers,
        json={
            "currentDay": 7,
            "checklistProgress": {"completed": 7, "total": 7},
            "documentProgress": {"uploaded": 1, "required": 1},
            "reviewStatus": "approved",
            "reportStatus": "ready_for_review",
        },
    )
    assert workflow.status_code == 200, workflow.text

    report = await async_client.post(
        f"/api/v1/reporting/engagements/{engagement_id}/statutory-audit",
        headers=headers,
        json={"allow_draft": True},
    )
    assert report.status_code == 201, report.text

    opinion = await async_client.post(
        f"/api/v1/engagements/engagements/{engagement_id}/opinion",
        headers=headers,
        json={},
    )
    assert opinion.status_code == 201, opinion.text

    seal_session = await async_client.post(
        f"/api/v1/engagements/{engagement_id}/seal-session",
        headers=headers,
        json={
            "required_signatures": 1,
            "created_by": "asha.rao@example.com",
            "partner_emails": ["asha.rao@example.com"],
        },
    )
    assert seal_session.status_code == 201, seal_session.text
    seal_session_id = seal_session.json()["id"]

    pre_sign = await async_client.get(
        f"/api/v1/seal-sessions/{seal_session_id}/pre-sign-summary",
        headers=headers,
    )
    assert pre_sign.status_code == 200, pre_sign.text
    assert pre_sign.json()["client_name"] == "CA Demo First Audit Private Limited"

    signed = await async_client.post(
        f"/api/v1/seal-sessions/{seal_session_id}/sign",
        headers=headers,
        json={
            "partner_user_id": "asha-ignored-by-auth",
            "partner_email": "asha.rao@example.com",
            "role": "ENGAGEMENT_PARTNER",
            "jurisdiction": "IN",
            "override_count_acknowledged": 0,
            "override_ack_confirmed": True,
            "ca_icai_reg_no": "FCA-123456",
        },
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["can_seal"] is True

    sealed = await async_client.post(
        f"/api/v1/engagements/engagements/{engagement_id}/seal",
        headers=headers,
    )
    assert sealed.status_code == 201, sealed.text
    assert sealed.json()["status"] == "success"

    blocked_upload = await async_client.post(
        f"/api/v1/engagements/{engagement_id}/evidence",
        headers=headers,
        files={"file": ("after-seal.png", PNG_1X1, "image/png")},
    )
    assert blocked_upload.status_code == 409, blocked_upload.text
