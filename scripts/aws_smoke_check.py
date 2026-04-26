#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


REQUIRED_OPENAPI_PATHS = {
    "/api/v1/mca/engagements/{engagement_id}/company-master",
    "/api/v1/reporting/engagements/{engagement_id}/statutory-audit",
    "/api/v1/reporting/reports/{report_id}/artifact",
    "/api/v1/reporting/reports/{report_id}/artifact/persist",
    "/api/v1/gst/engagements/{engagement_id}/reconcile/gstr1-vs-books",
    "/api/v1/erp/engagements/{engagement_id}/tally/trial-balance/import",
}


def request_json(base_url: str, path: str, *, api_key: str | None = None) -> tuple[int, dict]:
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return exc.code, parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a deployed Arkashri API.")
    parser.add_argument("--base-url", required=True, help="Deployed API base URL, for example https://api.example.com")
    parser.add_argument("--api-key", default=None, help="Optional API key for authenticated smoke checks")
    args = parser.parse_args()

    failures: list[str] = []

    ready_status, ready_payload = request_json(args.base_url, "/readyz")
    if ready_status != 200 or ready_payload.get("status") != "ready":
        failures.append(f"/readyz failed: status={ready_status} payload={ready_payload}")

    health_status, health_payload = request_json(args.base_url, "/health")
    if health_status not in {200, 503}:
        failures.append(f"/health returned unexpected status={health_status} payload={health_payload}")

    openapi_status, openapi_payload = request_json(args.base_url, "/openapi.json")
    if openapi_status != 200:
        failures.append(f"/openapi.json failed: status={openapi_status} payload={openapi_payload}")
    else:
        paths = set((openapi_payload.get("paths") or {}).keys())
        missing_paths = sorted(REQUIRED_OPENAPI_PATHS - paths)
        if missing_paths:
            failures.append(f"OpenAPI is missing required India audit paths: {missing_paths}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print("Arkashri deployment smoke check passed.")
    print(f"Base URL: {args.base_url.rstrip('/')}")
    print(f"Health status: {health_payload.get('status', 'unknown')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
