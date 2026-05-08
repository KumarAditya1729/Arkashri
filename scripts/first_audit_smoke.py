#!/usr/bin/env python3
"""Run the Arkashri first-audit production smoke flow.

This script intentionally creates a demo engagement and seals it. Use it only
with a seeded CA/operator account and an environment intended for smoke data.
"""
from __future__ import annotations

import base64
import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGA"
    "WjR9awAAAABJRU5ErkJggg=="
)


@dataclass
class SmokeConfig:
    backend_url: str
    tenant: str
    email: str
    password: str
    ca_icai_reg_no: str
    allow_write: bool


class SmokeFailure(RuntimeError):
    pass


def env_config() -> SmokeConfig:
    backend_url = os.getenv("ARKASHRI_BACKEND_URL", "").rstrip("/")
    tenant = os.getenv("ARKASHRI_SMOKE_TENANT", "default_tenant")
    email = os.getenv("ARKASHRI_SMOKE_EMAIL", "")
    password = os.getenv("ARKASHRI_SMOKE_PASSWORD", "")
    ca_icai_reg_no = os.getenv("ARKASHRI_SMOKE_CA_ICAI_REG_NO", "FCA-123456")
    allow_write = os.getenv("ARKASHRI_SMOKE_ALLOW_WRITE") == "1"

    missing = [
        name
        for name, value in {
            "ARKASHRI_BACKEND_URL": backend_url,
            "ARKASHRI_SMOKE_EMAIL": email,
            "ARKASHRI_SMOKE_PASSWORD": password,
        }.items()
        if not value
    ]
    if missing:
        raise SmokeFailure(f"Missing required environment variable(s): {', '.join(missing)}")
    if not allow_write:
        raise SmokeFailure(
            "Refusing to create audit records. Set ARKASHRI_SMOKE_ALLOW_WRITE=1 "
            "when you are ready to run the first-audit write smoke."
        )

    return SmokeConfig(
        backend_url=backend_url,
        tenant=tenant,
        email=email,
        password=password,
        ca_icai_reg_no=ca_icai_reg_no,
        allow_write=allow_write,
    )


def api_url(cfg: SmokeConfig, path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{cfg.backend_url}{normalized}"


def assert_status(response: httpx.Response, expected: int | set[int], label: str) -> dict[str, Any]:
    expected_set = {expected} if isinstance(expected, int) else expected
    if response.status_code not in expected_set:
        raise SmokeFailure(
            f"{label} failed: expected {sorted(expected_set)}, got {response.status_code}: {response.text[:1000]}"
        )
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()


def main() -> int:
    cfg = env_config()
    timeout = httpx.Timeout(30.0, connect=10.0)

    with httpx.Client(timeout=timeout) as client:
        health = client.get(api_url(cfg, "/health"))
        assert_status(health, {200, 503}, "health probe")
        print("[ok] backend health endpoint reachable")

        login = client.post(
            api_url(cfg, "/api/v1/token/"),
            headers={"X-Arkashri-Tenant": cfg.tenant},
            json={"email": cfg.email, "password": cfg.password},
        )
        login_body = assert_status(login, 200, "login")
        token = login_body["access_token"]
        headers = {"Authorization": f"Bearer {token}", "X-Arkashri-Tenant": cfg.tenant}
        print("[ok] authenticated as seeded CA/operator")

        created = client.post(
            api_url(cfg, "/api/v1/engagements/engagements"),
            headers=headers,
            json={
                "tenant_id": "client_payload_must_be_ignored",
                "jurisdiction": "IN",
                "client_name": "Arkashri CA Smoke Audit Private Limited",
                "engagement_type": "STATUTORY_AUDIT",
                "auditType": "statutory_audit",
                "independence_cleared": True,
                "kyc_cleared": True,
                "conflict_check_notes": "Smoke run independence and KYC verified by CA operator.",
            },
        )
        engagement = assert_status(created, 201, "create engagement")
        engagement_id = engagement["id"]
        if engagement["tenant_id"] != cfg.tenant:
            raise SmokeFailure("Engagement tenant_id did not come from authenticated tenant.")
        print(f"[ok] engagement created: {engagement_id}")

        workspace = client.post(
            api_url(cfg, f"/api/v1/standards/engagements/{engagement_id}/india-workspace/bootstrap"),
            headers=headers,
        )
        assert_status(workspace, 200, "bootstrap India audit workspace")
        print("[ok] India statutory audit workspace bootstrapped")

        phase = client.post(
            api_url(cfg, f"/api/v1/engagements/{engagement_id}/phases"),
            headers=headers,
            json={"name": "Planning", "status": "IN_PROGRESS", "owner": "Engagement Partner", "progress": 25},
        )
        assert_status(phase, 201, "create planning phase")

        materiality = client.post(
            api_url(cfg, f"/api/v1/engagements/engagements/{engagement_id}/materiality"),
            headers=headers,
            json={
                "basis": "REVENUE",
                "basis_amount": 10_000_000,
                "overall_percentage": 5,
                "performance_percentage": 75,
                "trivial_threshold_percentage": 5,
                "notes": "Production smoke materiality benchmark.",
            },
        )
        assert_status(materiality, 201, "record materiality")

        risk = client.post(
            api_url(cfg, f"/api/v1/engagements/{engagement_id}/risks"),
            headers=headers,
            json={
                "title": "Revenue recognition cut-off risk",
                "area": "Revenue",
                "likelihood": "HIGH",
                "impact": "HIGH",
                "owner": "Engagement Partner",
            },
        )
        risk_body = assert_status(risk, 201, "create risk")

        control = client.post(
            api_url(cfg, f"/api/v1/engagements/{engagement_id}/controls"),
            headers=headers,
            json={
                "title": "Review sales cut-off after period end",
                "area": "Revenue",
                "control_type": "DETECTIVE",
                "frequency": "Annual",
                "owner": "Engagement Partner",
                "risk_id": risk_body["id"],
            },
        )
        control_body = assert_status(control, 201, "create control")

        tested = client.patch(
            api_url(cfg, f"/api/v1/engagements/{engagement_id}/controls/{control_body['id']}"),
            headers=headers,
            json={"status": "EFFECTIVE"},
        )
        assert_status(tested, 200, "mark control tested")

        evidence = client.post(
            api_url(cfg, f"/api/v1/engagements/{engagement_id}/evidence"),
            headers=headers,
            files={"file": ("sales-cutoff.png", PNG_1X1, "image/png")},
            data={"test_ref": "REV-CUT-001"},
        )
        assert_status(evidence, 201, "upload evidence")
        print("[ok] planning, materiality, risk, control testing, and evidence persisted")

        ai_log = client.post(
            api_url(cfg, "/api/v1/usas/ai-governance-logs"),
            headers=headers,
            json={
                "tenant_id": "client_payload_must_be_ignored",
                "jurisdiction": "IN",
                "decision_id": f"{engagement_id}:planning",
                "model_used": "GPT-4o",
                "decision_rationale": (
                    "Source binding: SA 315 risk identification; CA reviewed revenue cut-off risk "
                    "and agreed to targeted procedures."
                ),
                "human_override": True,
                "override_reason": "CA accepted after source review.",
            },
        )
        ai_body = assert_status(ai_log, 201, "record AI governance log")
        if ai_body["tenant_id"] != cfg.tenant:
            raise SmokeFailure("AI governance log tenant_id did not come from authenticated tenant.")
        print("[ok] AI governance log bound to authenticated tenant")

        workflow = client.patch(
            api_url(cfg, f"/api/v1/engagements/engagements/{engagement_id}/workflow"),
            headers=headers,
            json={
                "currentDay": 7,
                "checklistProgress": {"completed": 7, "total": 7},
                "documentProgress": {"uploaded": 1, "required": 1},
                "reviewStatus": "approved",
                "reportStatus": "ready_for_review",
            },
        )
        assert_status(workflow, 200, "persist workflow state")

        report = client.post(
            api_url(cfg, f"/api/v1/reporting/engagements/{engagement_id}/statutory-audit"),
            headers=headers,
            json={"allow_draft": True},
        )
        assert_status(report, 201, "generate statutory report")

        opinion = client.post(
            api_url(cfg, f"/api/v1/engagements/engagements/{engagement_id}/opinion"),
            headers=headers,
            json={},
        )
        assert_status(opinion, 201, "generate opinion")
        print("[ok] report and draft opinion generated")

        seal_session = client.post(
            api_url(cfg, f"/api/v1/engagements/{engagement_id}/seal-session"),
            headers=headers,
            json={
                "required_signatures": 1,
                "created_by": cfg.email,
                "partner_emails": [cfg.email],
            },
        )
        seal_session_body = assert_status(seal_session, 201, "create seal session")

        pre_sign = client.get(
            api_url(cfg, f"/api/v1/seal-sessions/{seal_session_body['id']}/pre-sign-summary"),
            headers=headers,
        )
        assert_status(pre_sign, 200, "load pre-sign summary")

        signed = client.post(
            api_url(cfg, f"/api/v1/seal-sessions/{seal_session_body['id']}/sign"),
            headers=headers,
            json={
                "partner_user_id": "payload-ignored",
                "partner_email": cfg.email,
                "role": "ENGAGEMENT_PARTNER",
                "jurisdiction": "IN",
                "override_count_acknowledged": 0,
                "override_ack_confirmed": True,
                "ca_icai_reg_no": cfg.ca_icai_reg_no,
            },
        )
        assert_status(signed, 200, "partner sign-off")

        sealed = client.post(
            api_url(cfg, f"/api/v1/engagements/engagements/{engagement_id}/seal"),
            headers=headers,
        )
        assert_status(sealed, 201, "seal engagement")

        blocked = client.post(
            api_url(cfg, f"/api/v1/engagements/{engagement_id}/evidence"),
            headers=headers,
            files={"file": ("after-seal.png", PNG_1X1, "image/png")},
        )
        assert_status(blocked, 409, "WORM evidence upload rejection after seal")
        print("[ok] partner sign-off, seal, and post-seal immutability verified")
        print(f"\nFIRST AUDIT SMOKE PASSED: {engagement_id}")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print(f"FIRST AUDIT SMOKE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
