#!/usr/bin/env python3
"""Smoke test the Arkashri automation layer against a deployed backend."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def request(method: str, url: str, *, token: str | None = None, body: dict | None = None) -> tuple[int, str]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json", "X-Arkashri-Tenant": env("ARKASHRI_SMOKE_TENANT", "default_tenant")}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def main() -> int:
    backend = env("ARKASHRI_BACKEND_URL").rstrip("/")
    engagement_id = env("ARKASHRI_SMOKE_ENGAGEMENT_ID")
    token = env("ARKASHRI_SMOKE_BEARER_TOKEN") or None
    if not backend or not engagement_id:
        print("Set ARKASHRI_BACKEND_URL and ARKASHRI_SMOKE_ENGAGEMENT_ID.", file=sys.stderr)
        return 2

    checks = [
        ("GET", f"{backend}/api/v1/audit-automation/capabilities", None),
        ("GET", f"{backend}/api/v1/audit-automation/engagements/{engagement_id}/pack", None),
        ("POST", f"{backend}/api/v1/audit-automation/engagements/{engagement_id}/sampling-plan", {"sample_size": 5}),
        ("POST", f"{backend}/api/v1/audit-automation/engagements/{engagement_id}/agents/run", {}),
    ]
    failures = []
    for method, url, body in checks:
        status, text = request(method, url, token=token, body=body)
        print(json.dumps({"method": method, "url": url, "status": status, "body": text[:200]}))
        if status < 200 or status >= 400:
            failures.append((method, url, status))
    if failures:
        print(f"Automation smoke failed: {failures}", file=sys.stderr)
        return 1
    print("Automation smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
